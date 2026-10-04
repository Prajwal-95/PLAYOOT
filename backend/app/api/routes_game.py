"""Game lifecycle, lobby and team routes (REST).

Mutations that happen *before* or *around* gameplay (creating a game, taking a
seat, team management) go over REST so failures are ordinary, informative HTTP
errors.  Everything that happens *during* gameplay - host commands, questions,
answers, timers - goes over the WebSocket.

Both paths funnel into the same server-side services and the same
``GameEngine``, and every one of them broadcasts the corresponding realtime
event to the room.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_optional_user, get_player_token
from app.database import get_session
from app.game.errors import GameError, GameErrorCode
from app.models.game import Player, Team
from app.models.user import User
from app.schemas.api import (
    GameCreateIn,
    GameLookupOut,
    JoinGameIn,
    JoinGameOut,
    LobbyOut,
    TeamCreateIn,
    TeamJoinIn,
    TeamOut,
)
from app.services import game_service
from app.services.results_service import build_results

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/games", tags=["games"])


async def _lookup(session: AsyncSession, pin: str):
    game = await game_service.get_game_by_pin(session, pin)
    engine = await game_service.get_engine(session, game.game_pin)
    return game, engine


async def _team_name(session: AsyncSession, team_id: int | None) -> str | None:
    if team_id is None:
        return None
    team = await session.get(Team, team_id)
    return team.name if team else None


# ------------------------------------------------------------------- create
@router.post("", response_model=GameLookupOut, status_code=status.HTTP_201_CREATED)
async def create_game(
    payload: GameCreateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    game = await game_service.create_game(
        session, host=user, quiz_id=payload.quiz_id, mode=payload.mode
    )
    engine = await game_service.get_engine(session, game.game_pin)
    return game_service.game_lookup_out(game, engine)


# ------------------------------------------------------------------- lookup
@router.get("/{pin}", response_model=GameLookupOut)
async def lookup_game(pin: str, session: AsyncSession = Depends(get_session)) -> dict:
    game, engine = await _lookup(session, pin)
    return game_service.game_lookup_out(game, engine)


@router.get("/{pin}/lobby", response_model=LobbyOut)
async def get_lobby(pin: str, session: AsyncSession = Depends(get_session)) -> dict:
    _game, engine = await _lookup(session, pin)
    return await game_service.lobby_snapshot(session, engine)


@router.get("/{pin}/teams", response_model=list[TeamOut])
async def list_teams(pin: str, session: AsyncSession = Depends(get_session)) -> list[dict]:
    _game, engine = await _lookup(session, pin)
    snapshot = await game_service.lobby_snapshot(session, engine)
    return snapshot["teams"]

# --------------------------------------------------------------------- join
@router.post("/{pin}/join", response_model=JoinGameOut, status_code=status.HTTP_201_CREATED)
async def join_game(
    pin: str,
    payload: JoinGameIn,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_optional_user),
) -> dict:
    player, token = await game_service.join_game(
        session,
        pin=pin,
        nickname=payload.nickname,
        user_id=user.id if user else None,
        team_id=payload.team_id,
    )
    game = await game_service.get_game_by_pin(session, pin)
    engine = await game_service.get_engine(session, game.game_pin)
    return {
        "player": game_service.player_out(
            player, team_name=await _team_name(session, player.team_id)
        ),
        "player_token": token,
        "game": game_service.game_lookup_out(game, engine),
    }


@router.post("/{pin}/rejoin", response_model=JoinGameOut)
async def rejoin_game(
    pin: str, payload: JoinGameIn, session: AsyncSession = Depends(get_session)
) -> dict:
    """Resume an existing seat after the player token was lost.

    Only allowed for a nickname that is currently *disconnected*, so nobody can
    hijack a seat that is actively being played.
    """
    from app.core.security import create_player_token

    game = await game_service.get_game_by_pin(session, pin)
    engine = await game_service.get_engine(session, game.game_pin)
    nickname = " ".join(payload.nickname.split()).lower()
    player = await session.scalar(
        select(Player).where(
            Player.game_id == engine.id, func.lower(Player.nickname) == nickname
        )
    )
    if player is None:
        raise GameError(
            GameErrorCode.PLAYER_NOT_IN_GAME,
            "No player with that nickname is in this game.",
            status_code=404,
        )
    # Presence is owned by the live engine, not the persisted row: the socket
    # layer only tracks `connected` in memory, so the database value would stay
    # stale and let anyone hijack a seat that is actively being played.
    live = engine.players.get(player.id)
    is_connected = live.connected if live is not None else player.connected
    if is_connected:
        raise GameError(
            GameErrorCode.BAD_REQUEST,
            "That nickname is currently connected in this game.",
            status_code=409,
        )
    token = create_player_token(player.id, engine.id, engine.pin)
    return {
        "player": game_service.player_out(
            player, team_name=await _team_name(session, player.team_id)
        ),
        "player_token": token,
        "game": game_service.game_lookup_out(game, engine),
    }


@router.post("/{pin}/leave", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def leave_game(
    pin: str,
    session: AsyncSession = Depends(get_session),
    player_token: str = Depends(get_player_token),
) -> None:
    player, _engine = await game_service.require_player(session, player_token=player_token)
    await game_service.leave_game(session, pin=pin, player_id=player.id)
    return None


# -------------------------------------------------------------------- teams
@router.post("/{pin}/teams", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def create_team(
    pin: str,
    payload: TeamCreateIn,
    session: AsyncSession = Depends(get_session),
    player_token: str = Depends(get_player_token),
) -> dict:
    player, _engine = await game_service.require_player(session, player_token=player_token)
    if payload.player_id is not None and payload.player_id != player.id:
        raise GameError(
            GameErrorCode.UNAUTHORIZED, "You can only create a team for yourself."
        )
    team = await game_service.create_team(
        session, pin=pin, name=payload.name, player_id=player.id, join=payload.join
    )
    _game, engine = await _lookup(session, pin)
    snapshot = await game_service.lobby_snapshot(session, engine)
    return next(t for t in snapshot["teams"] if t["team_id"] == team.id)


@router.post("/{pin}/teams/join", response_model=TeamOut)
async def join_team(
    pin: str,
    payload: TeamJoinIn,
    session: AsyncSession = Depends(get_session),
    player_token: str = Depends(get_player_token),
) -> dict:
    player, engine = await game_service.require_player(session, player_token=player_token)
    team = await game_service.assign_player_to_team(
        session, engine=engine, player_row=player, team_id=payload.team_id
    )
    snapshot = await game_service.lobby_snapshot(session, engine)
    return next(t for t in snapshot["teams"] if t["team_id"] == team.id)


@router.post("/{pin}/teams/leave", response_model=list[TeamOut])
async def leave_team(
    pin: str,
    session: AsyncSession = Depends(get_session),
    player_token: str = Depends(get_player_token),
) -> list[dict]:
    player, _engine = await game_service.require_player(session, player_token=player_token)
    await game_service.leave_team(session, pin=pin, player_id=player.id)
    _game, engine = await _lookup(session, pin)
    snapshot = await game_service.lobby_snapshot(session, engine)
    return snapshot["teams"]


@router.get("/{pin}/results")
async def get_results(pin: str, session: AsyncSession = Depends(get_session)) -> dict:
    return await build_results(session, pin=pin)