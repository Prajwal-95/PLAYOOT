"""The gameplay WebSocket.

Everything that happens during a live game flows through here.  The handler is
deliberately thin: it authenticates the socket, then translates inbound actions
into calls on the authoritative :class:`~app.game.engine.GameEngine`.  It
contains **no** game rules of its own.

Authentication
--------------
``/ws/game/{pin}?player_token=...``   a joined player (from
                                      ``POST /api/games/{pin}/join``)
``/ws/game/{pin}?token=...``          the host (the same JWT the REST API uses)

A player token is verified *and* the player is re-checked against the game on
every connection, so a socket can never attach to a game it does not belong to.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.pin import normalise_pin
from app.core.security import TOKEN_TYPE_HOST, TOKEN_TYPE_PLAYER, decode_token
from app.game.engine import GameEngine
from app.game.errors import GameError, GameErrorCode
from app.game.events import (
    HOST_ACTIONS,
    WSClientAction,
    WSEventType,
    envelope,
    parse_client_message,
)
from app.game.manager import Connection, manager
from app.game.registry import get_registry

logger = logging.getLogger(__name__)
router = APIRouter()

#: WebSocket close codes (4000-4999 is the application-private range).
CLOSE_BAD_REQUEST = 4400
CLOSE_UNAUTHORIZED = 4401
CLOSE_NOT_FOUND = 4404
CLOSE_CONFLICT = 4409


async def _fail(
    websocket: WebSocket, code: GameErrorCode, message: str, close_code: int
) -> None:
    """Report a structured failure and close the socket."""
    try:
        await websocket.send_json(
            envelope(WSEventType.GAME_ERROR, {"code": code.value, "message": message})
        )
    except Exception:  # pragma: no cover - socket already gone
        pass
    try:
        await websocket.close(code=close_code)
    except Exception:  # pragma: no cover
        pass


@router.websocket("/ws/game/{pin}")
async def game_socket(
    websocket: WebSocket,
    pin: str,
    token: str | None = Query(default=None, description="Host access token"),
    player_token: str | None = Query(default=None, description="Player session token"),
) -> None:
    await websocket.accept()
    connection: Connection | None = None
    engine: GameEngine | None = None

    # ------------------------------------------------------ resolve the game
    try:
        normalised = normalise_pin(pin)
    except GameError as exc:
        await _fail(websocket, exc.code, exc.message, CLOSE_BAD_REQUEST)
        return

    try:
        engine = await get_registry().get(normalised)
    except GameError as exc:
        await _fail(websocket, exc.code, exc.message, CLOSE_NOT_FOUND)
        return
    except Exception:
        logger.exception("failed to load engine for pin %s", normalised)
        await _fail(
            websocket,
            GameErrorCode.INTERNAL_ERROR,
            "The game could not be loaded.",
            CLOSE_CONFLICT,
        )
        return

    # -------------------------------------------------- resolve the identity
    role: str
    player_id: int | None = None
    user_id: int | None = None

    if player_token:
        payload = decode_token(player_token, expected_type=TOKEN_TYPE_PLAYER)
        if payload is None:
            await _fail(
                websocket,
                GameErrorCode.UNAUTHORIZED,
                "Your player session has expired. Please rejoin the game.",
                CLOSE_UNAUTHORIZED,
            )
            return
        try:
            candidate_id = int(payload["sub"])
            candidate_game = int(payload["gid"])
        except (KeyError, TypeError, ValueError):
            await _fail(
                websocket,
                GameErrorCode.UNAUTHORIZED,
                "Malformed player token.",
                CLOSE_UNAUTHORIZED,
            )
            return
        if candidate_game != engine.id or candidate_id not in engine.players:
            await _fail(
                websocket,
                GameErrorCode.PLAYER_NOT_IN_GAME,
                "You are not a player in this game.",
                CLOSE_UNAUTHORIZED,
            )
            return
        role, player_id = "player", candidate_id
    elif token:
        payload = decode_token(token, expected_type=TOKEN_TYPE_HOST)
        if payload is None:
            await _fail(
                websocket,
                GameErrorCode.UNAUTHORIZED,
                "Invalid host token.",
                CLOSE_UNAUTHORIZED,
            )
            return
        try:
            candidate_user = int(payload["sub"])
        except (KeyError, TypeError, ValueError):
            await _fail(
                websocket,
                GameErrorCode.UNAUTHORIZED,
                "Malformed host token.",
                CLOSE_UNAUTHORIZED,
            )
            return
        if candidate_user != engine.host_id:
            await _fail(
                websocket,
                GameErrorCode.UNAUTHORIZED_HOST,
                "You are not the host of this game.",
                CLOSE_UNAUTHORIZED,
            )
            return
        role, user_id = "host", candidate_user
    else:
        await _fail(
            websocket,
            GameErrorCode.UNAUTHORIZED,
            "A host or player token is required to connect.",
            CLOSE_UNAUTHORIZED,
        )
        return

    # ------------------------------------------------------------- register
    connection = Connection(
        websocket=websocket,
        role=role,  # type: ignore[arg-type]
        game_pin=engine.pin,
        game_id=engine.id,
        player_id=player_id,
        user_id=user_id,
    )
    await manager.register(connection)

    try:
        if player_id is not None:
            live = await engine.set_player_connected(player_id, True, broadcast=True)
            if live is None:
                await _fail(
                    websocket,
                    GameErrorCode.PLAYER_NOT_IN_GAME,
                    "You are not a player in this game.",
                    CLOSE_NOT_FOUND,
                )
                return

        await manager.send(
            connection,
            WSEventType.CONNECTED,
            {
                "connectionId": connection.id,
                "role": role,
                "playerId": player_id,
                "userId": user_id,
                "gameId": engine.id,
                "gamePin": engine.pin,
                "mode": engine.mode,
                "state": engine.state.value,
            },
        )
        # full authoritative snapshot: this is what makes reconnection seamless
        await manager.send(
            connection,
            WSEventType.STATE_SYNC,
            engine.snapshot(for_player_id=player_id),
        )

        # ------------------------------------------------------- action loop
        while True:
            raw = await websocket.receive_json()
            await _handle_action(connection, engine, raw)

    except WebSocketDisconnect:
        logger.debug("socket disconnected: %s (%s)", connection.id, role)
    except Exception:
        logger.exception("unexpected socket failure for %s", connection.id)
    finally:
        await manager.unregister(connection)
        if player_id is not None and engine is not None:
            # a dropped socket must never destroy progress - only presence
            try:
                await engine.set_player_connected(player_id, False, broadcast=True)
            except Exception:  # pragma: no cover
                logger.exception("failed to mark player %s disconnected", player_id)


async def _handle_action(connection: Connection, engine: GameEngine, raw: Any) -> None:
    """Translate one inbound frame into an engine call."""
    try:
        action, payload = parse_client_message(raw)
    except ValueError as exc:
        await manager.send(
            connection,
            WSEventType.GAME_ERROR,
            {"code": GameErrorCode.BAD_REQUEST.value, "message": str(exc)},
        )
        return

    try:
        if action is WSClientAction.PING:
            await manager.send(connection, WSEventType.PONG, {})
            return

        if action is WSClientAction.REQUEST_STATE:
            await manager.send(
                connection,
                WSEventType.STATE_SYNC,
                engine.snapshot(for_player_id=connection.player_id),
            )
            return

        if action in HOST_ACTIONS:
            # authorization lives in the engine, not here
            if action is WSClientAction.START_GAME:
                await engine.start_game(connection.user_id)
            elif action is WSClientAction.NEXT_QUESTION:
                await engine.next_question(connection.user_id)
            elif action is WSClientAction.END_QUESTION:
                engine._require_host(connection.user_id)
                closed = await engine.finalize_current_question("host-ended-question")
                if not closed:
                    raise GameError(
                        GameErrorCode.NO_ACTIVE_QUESTION,
                        "There is no question in progress to end.",
                    )
            elif action is WSClientAction.END_GAME:
                await engine.end_game(connection.user_id)
            elif action is WSClientAction.CANCEL_GAME:
                await engine.cancel_game(connection.user_id)
            return

        if action is WSClientAction.SUBMIT_ANSWER:
            if connection.player_id is None:
                raise GameError(
                    GameErrorCode.UNAUTHORIZED,
                    "Only players can submit answers.",
                    status_code=403,
                )
            question_id = payload.get("questionId")
            if question_id is None:
                raise GameError(
                    GameErrorCode.BAD_REQUEST, "An answer must include 'questionId'."
                )
            if "answer" not in payload:
                raise GameError(GameErrorCode.BAD_REQUEST, "An answer must include 'answer'.")
            await engine.submit_answer(
                player_id=connection.player_id,
                question_id=question_id,
                answer_index=payload.get("answer"),
            )
            return

        raise GameError(GameErrorCode.BAD_REQUEST, f"Unsupported action '{action.value}'.")

    except GameError as exc:
        # expected, user-presentable failure - report it, keep the socket open
        await manager.send(connection, WSEventType.GAME_ERROR, exc.to_payload())
    except Exception:
        logger.exception("action %s failed for connection %s", action, connection.id)
        await manager.send(
            connection,
            WSEventType.GAME_ERROR,
            {
                "code": GameErrorCode.INTERNAL_ERROR.value,
                "message": "Something went wrong handling that action.",
            },
        )