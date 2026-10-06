"""Host-authoritative participant removal.

The host may eject somebody, but only under the rules that keep the game
honest and the seat pool consistent:

* always allowed while the lobby is open,
* during play only for a DISCONNECTED participant - never mid answer,
* only the game's own host,
* the old player token must stop working afterwards,
* the roster broadcast must happen AFTER the roster actually changed,
* the participant's answers are purged with them.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from conftest import join

BACKEND_DIR = Path(__file__).resolve().parents[1]


def recv_until(ws, wanted, limit: int = 40):
    """Read frames until one of ``wanted`` arrives."""
    wanted = {wanted} if isinstance(wanted, str) else set(wanted)
    seen = []
    for _ in range(limit):
        message = ws.receive_json()
        seen.append(message["type"])
        if message["type"] in wanted:
            return message
    raise AssertionError(f"never received {wanted}; saw {seen}")


def send(ws, action: str, payload: dict | None = None) -> None:
    ws.send_json({"type": action, "payload": payload or {}})


def _count_answers(pin: str) -> int:
    """How many ``answers`` rows still exist for this game."""
    from sqlalchemy import func, select

    from app.database import SessionLocal
    from app.models.game import Answer, GameSession

    async def _query() -> int:
        async with SessionLocal() as session:
            game_id = await session.scalar(
                select(GameSession.id).where(GameSession.game_pin == pin)
            )
            if game_id is None:
                return -1
            count = await session.scalar(
                select(func.count())
                .select_from(Answer)
                .where(Answer.game_id == game_id)
            )
            return int(count or 0)

    return asyncio.run(_query())


# ===========================================================================
# Lobby
# ===========================================================================
def test_host_can_remove_a_participant_in_the_lobby(client, host, game):
    pin = game["game_pin"]
    session = join(client, game, "Ada")
    player_id = session["player"]["player_id"]

    response = client.delete(
        f"/api/games/{pin}/players/{player_id}", headers=host["headers"]
    )
    assert response.status_code == 204, response.text

    lobby = client.get(f"/api/games/{pin}/lobby").json()
    assert lobby["players"] == []

    # The seat and the nickname are genuinely free again.
    assert (
        client.post(f"/api/games/{pin}/join", json={"nickname": "Ada"}).status_code
        == 201
    )


def test_only_the_owning_host_may_remove_a_participant(client, other_host, game):
    pin = game["game_pin"]
    player_id = join(client, game, "Ada")["player"]["player_id"]

    response = client.delete(
        f"/api/games/{pin}/players/{player_id}", headers=other_host["headers"]
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "UNAUTHORIZED_HOST"

    lobby = client.get(f"/api/games/{pin}/lobby").json()
    assert len(lobby["players"]) == 1


def test_removal_requires_host_authentication(client, game):
    pin = game["game_pin"]
    player_id = join(client, game, "Ada")["player"]["player_id"]

    assert client.delete(f"/api/games/{pin}/players/{player_id}").status_code == 401


def test_removing_a_stranger_is_refused(client, host, game):
    pin = game["game_pin"]
    join(client, game, "Ada")

    response = client.delete(
        f"/api/games/{pin}/players/999999", headers=host["headers"]
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "PLAYER_NOT_IN_GAME"

    assert len(client.get(f"/api/games/{pin}/lobby").json()["players"]) == 1


def test_the_removed_participants_old_token_is_dead(client, host, game):
    """De-authorising the seat is the whole point: the old token must not
    keep working over REST *or* over the gameplay socket."""
    pin = game["game_pin"]
    session = join(client, game, "Ada")
    token = session["player_token"]
    player_id = session["player"]["player_id"]

    assert (
        client.delete(
            f"/api/games/{pin}/players/{player_id}", headers=host["headers"]
        ).status_code
        == 204
    )

    # REST: the old credential can no longer act on this game.
    response = client.post(f"/api/games/{pin}/leave", headers={"X-Player-Token": token})
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "PLAYER_NOT_IN_GAME"

    # WebSocket: refused at the handshake, never attached to the room.
    with client.websocket_connect(f"/ws/game/{pin}?player_token={token}") as ws:
        message = recv_until(ws, "GAME_ERROR")
        assert message["payload"]["code"] in {"UNAUTHORIZED", "PLAYER_NOT_IN_GAME"}

    # ...and a completely fresh join still works.
    assert (
        client.post(f"/api/games/{pin}/join", json={"nickname": "Ada"}).status_code
        == 201
    )


# ===========================================================================
# During play
# ===========================================================================
def test_a_connected_participant_cannot_be_yanked_out_mid_question(
    client, host, game
):
    """Never mid-answer: an actively connected participant is untouchable
    while the quiz is running."""
    pin = game["game_pin"]
    session = join(client, game, "Ada")
    player_id = session["player"]["player_id"]

    with client.websocket_connect(f"/ws/game/{pin}?token={host['token']}") as host_ws:
        host_ws.receive_json()  # CONNECTED
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={session['player_token']}"
        ) as player_ws:
            player_ws.receive_json()  # CONNECTED
            send(host_ws, "START_GAME")
            recv_until(host_ws, "QUESTION_STARTED")

            response = client.delete(
                f"/api/games/{pin}/players/{player_id}", headers=host["headers"]
            )
            assert response.status_code == 400, response.text
            assert response.json()["detail"]["code"] == "BAD_REQUEST"

            lobby = client.get(f"/api/games/{pin}/lobby").json()
            assert [p["player_id"] for p in lobby["players"]] == [player_id]

            # let the server go idle before the socket is torn down
            send(player_ws, "PING")
            recv_until(player_ws, "PONG")


def test_a_disconnected_participant_can_be_removed_during_play(client, host, game):
    pin = game["game_pin"]
    session = join(client, game, "Ada")
    player_id = session["player"]["player_id"]

    with client.websocket_connect(f"/ws/game/{pin}?token={host['token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={session['player_token']}"
        ) as player_ws:
            player_ws.receive_json()
            send(host_ws, "START_GAME")
            recv_until(host_ws, "QUESTION_STARTED")
            # drain the socket so the server is back at its receive loop
            # before this session is torn down
            send(player_ws, "PING")
            recv_until(player_ws, "PONG")

        # socket closed -> presence flips to disconnected, score preserved
        recv_until(host_ws, "PLAYER_UPDATED")

        response = client.delete(
            f"/api/games/{pin}/players/{player_id}", headers=host["headers"]
        )
        assert response.status_code == 204, response.text

        # The roster broadcast happens after the removal, so the host's very
        # next snapshot is already empty.
        send(host_ws, "REQUEST_STATE")
        sync = recv_until(host_ws, "STATE_SYNC")["payload"]
        assert sync["players"] == []


def test_removal_purges_the_participants_answers(client, host, game):
    pin = game["game_pin"]
    session = join(client, game, "Ada")
    player_id = session["player"]["player_id"]

    with client.websocket_connect(f"/ws/game/{pin}?token={host['token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={session['player_token']}"
        ) as player_ws:
            player_ws.receive_json()
            send(host_ws, "START_GAME")
            q1 = recv_until(host_ws, "QUESTION_STARTED")["payload"]
            send(
                player_ws,
                "SUBMIT_ANSWER",
                {"questionId": q1["questionId"], "answer": 0},
            )
            recv_until(player_ws, "ANSWER_SUBMITTED")
            # let the server return to its receive loop before this session
            # is torn down, so the PLAYER_ANSWERED broadcast can land
            send(player_ws, "PING")
            recv_until(player_ws, "PONG")

        recv_until(host_ws, "PLAYER_ANSWERED")

        assert _count_answers(pin) == 1, "the answer should be persisted"

        assert (
            client.delete(
                f"/api/games/{pin}/players/{player_id}", headers=host["headers"]
            ).status_code
            == 204
        )

        assert _count_answers(pin) == 0, "answers must be purged with the player"


# ===========================================================================
# Source-level guards for the ordering rules that are hard to observe live
# ===========================================================================
def _service_source() -> str:
    return (BACKEND_DIR / "app" / "services" / "game_service.py").read_text(
        encoding="utf-8"
    )


def _function_body(source: str, name: str) -> str:
    marker = f"async def {name}("
    assert marker in source, f"{name} not found"
    head, _, rest = source.partition(marker)
    next_def = rest.find("\nasync def ")
    return rest if next_def == -1 else rest[:next_def]


def test_removal_validates_purges_and_mutates_inside_one_critical_section():
    """Validation, the DB purge and the in-memory roster change must share one
    ``engine.lock`` section so a removal can never interleave with an answer."""
    body = _function_body(_service_source(), "remove_player_by_host")

    lock_at = body.index("async with engine.lock:")
    purge_at = body.index("session.delete(player)")
    drop_at = body.index("engine.drop_player(")

    assert lock_at < purge_at < drop_at


def test_the_roster_is_broadcast_only_after_the_player_is_gone():
    """Broadcasting first shipped a snapshot that still listed the removed
    player, so every client rendered them back onto the screen."""
    body = _function_body(_service_source(), "remove_player_by_host")
    assert body.index("engine.drop_player(") < body.index("broadcast_lobby_state(")
    assert "close_player" in body


def test_leave_game_also_broadcasts_after_the_roster_changed():
    body = _function_body(_service_source(), "leave_game")
    assert body.index("engine.remove_player(") < body.index("broadcast_lobby_state(")


def test_drop_player_is_memory_only():
    """The engine helper must never broadcast on its own - the caller owns the
    ordering between mutating the roster and announcing it."""
    source = (BACKEND_DIR / "app" / "game" / "engine.py").read_text(encoding="utf-8")
    head, _, rest = source.partition("def drop_player(")
    assert head, "drop_player is missing from the engine"
    tail = rest[: rest.find("\n    async def ")]
    assert "self._emit" not in tail
    assert "broadcast_lobby_state" not in tail
    assert "manager.broadcast" not in tail


def test_the_remove_player_route_is_registered():
    routes = (BACKEND_DIR / "app" / "api" / "routes_game.py").read_text(
        encoding="utf-8"
    )
    assert '@router.delete("/{pin}/players/{player_id}"' in routes
    assert "remove_player_by_host" in routes
