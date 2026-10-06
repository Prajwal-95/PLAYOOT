"""REST-side game services.

Division of labour:

* **this module** owns *persistence* and the request/response shape of the
  lobby - creating games, seating players, creating/joining/leaving teams.
* :class:`app.game.engine.GameEngine` owns *live state* and *gameplay*.

Anything that both concerns is done as one critical section on ``engine.lock``
so a capacity check and its write can never be interleaved.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.pin import generate_unique_pin, normalise_pin
from app.core.security import create_player_token
from app.game.engine import GameEngine
from app.game.errors import GameError, GameErrorCode
from app.game.events import WSEventType
from app.game.registry import get_registry
from app.game.states import JOINABLE_STATES, GameState
from app.models.game import GameSession, Player, Team
from app.models.quiz import Quiz
from app.models.user import User

logger = logging.getLogger(__name__)


# ------------------------------------------------------------- serialisation
def player_out(player: Player, *, team_name: str | None = None) -> dict:
    return {
        "player_id": player.id,
        "nickname": player.nickname,
        "score": player.score,
        "connected": player.connected,
        "team_id": player.team_id,
        "team_name": team_name,
    }


def team_out(team: Team, players: list[Player]) -> dict:
    members = [p for p in players if p.team_id == team.id]
    return {
        "team_id": team.id,
        "name": team.name,
        "score": team.score,
        "member_count": len(members),
        "max_size": settings.max_team_size,
        "is_full": len(members) >= settings.max_team_size,
        "members": [player_out(m, team_name=team.name) for m in members],
    }


def game_lookup_out(game: GameSession, engine: GameEngine) -> dict:
    return {
        "game_id": game.id,
        "game_pin": game.game_pin,
        "mode": game.mode,
        "status": engine.state.value,
        "quiz_id": game.quiz_id,
        "quiz_title": game.quiz.title if game.quiz else "Quiz",
        "question_count": len(engine.questions),
        "player_count": len(engine.players),
        "team_count": len(engine.teams),
        "max_team_size": settings.max_team_size,
        "joinable": engine.state in JOINABLE_STATES,
        "created_at": game.created_at,
    }


# -------------------------------------------------------------------- create
async def create_game(
    session: AsyncSession, *, host: User, quiz_id: int, mode: str
) -> GameSession:
    quiz = await session.get(Quiz, quiz_id)
    if quiz is None or quiz.creator_id != host.id:
        raise GameError(GameErrorCode.GAME_NOT_FOUND, "Quiz not found.", status_code=404)
    question_count = await session.scalar(
        select(func.count()).select_from(Quiz).join(Quiz.questions).where(Quiz.id == quiz_id)
    )
    if not question_count:
        raise GameError(
            GameErrorCode.NO_QUESTIONS,
            "Add at least one question to this quiz before hosting a game.",
        )
    game = GameSession(
        quiz_id=quiz_id,
        host_id=host.id,
        game_pin=await generate_unique_pin(session),
        mode=mode,
        status=GameState.LOBBY.value,
        current_question_index=-1,
    )
    session.add(game)
    await session.commit()
    await session.refresh(game)
    logger.info("game %s created for quiz %s by user %s", game.game_pin, quiz_id, host.id)
    return game


async def join_game(
    session: AsyncSession,
    *,
    pin: str,
    nickname: str,
    user_id: int | None = None,
    team_id: int | None = None,
) -> tuple[Player, str]:
    """Seat a player.  Returns the persisted row plus a resumable token."""
    engine = await get_engine(session, pin)

    if engine.state == GameState.CANCELLED:
        raise GameError(GameErrorCode.GAME_CANCELLED)
    if engine.state == GameState.FINISHED:
        raise GameError(GameErrorCode.GAME_ENDED)
    if engine.state not in JOINABLE_STATES:
        raise GameError(
            GameErrorCode.GAME_ALREADY_STARTED,
            "This game has already started - you can no longer join.",
        )
    if len(engine.players) >= settings.max_players_per_game:
        raise GameError(GameErrorCode.GAME_FULL)

    cleaned = " ".join((nickname or "").split())
    if not (
        settings.nickname_min_length <= len(cleaned) <= settings.nickname_max_length
    ):
        raise GameError(
            GameErrorCode.INVALID_NICKNAME,
            f"Nickname must be {settings.nickname_min_length}-"
            f"{settings.nickname_max_length} characters.",
        )
    taken = await session.scalar(
        select(Player.id).where(
            Player.game_id == engine.id, func.lower(Player.nickname) == cleaned.lower()
        )
    )
    if taken is not None:
        raise GameError(GameErrorCode.NICKNAME_TAKEN)

    if team_id is not None and engine.mode != "team":
        raise GameError(GameErrorCode.TEAM_MODE_REQUIRED)

    player = Player(
        game_id=engine.id, user_id=user_id, nickname=cleaned, team_id=None, connected=False
    )
    session.add(player)
    try:
        await session.commit()
    except IntegrityError as exc:  # unique (game_id, nickname) lost the race
        await session.rollback()
        raise GameError(GameErrorCode.NICKNAME_TAKEN) from exc
    await session.refresh(player)

    await engine.register_player(player)
    if team_id is not None:
        await assign_player_to_team(session, engine=engine, player_row=player, team_id=team_id)

    token = create_player_token(player.id, engine.id, engine.pin)
    return player, token


async def leave_game(session: AsyncSession, *, pin: str, player_id: int) -> None:
    """Remove a player.

    In the lobby the seat is freed entirely.  Once play has begun the player is
    only marked disconnected so their score is preserved and they can return.
    """
    engine = await get_engine(session, pin)
    player = await session.get(Player, player_id)
    if player is None or player.game_id != engine.id:
        raise GameError(GameErrorCode.PLAYER_NOT_IN_GAME)

    if engine.state in JOINABLE_STATES:
        await session.delete(player)
        await session.commit()
        await engine.broadcast_lobby_state(WSEventType.PLAYER_LEFT, {"playerId": player_id})
        await engine.remove_player(player_id, broadcast=False)
        return

    player.connected = False
    await session.commit()
    await engine.set_player_connected(player_id, False, broadcast=True)


# ---------------------------------------------------------------------- teams
async def assign_player_to_team(
    session: AsyncSession,
    *,
    engine: GameEngine,
    player_row: Player,
    team_id: int,
) -> Team:
    """Move a player onto a team, enforcing ``MAX_TEAM_SIZE`` server-side.

    The capacity check and the write happen inside one critical section, so five
    simultaneous joins to a 4-slot team can only ever seat four.
    """
    if engine.mode != "team":
        raise GameError(GameErrorCode.TEAM_MODE_REQUIRED)

    previous_team_id = player_row.team_id
    already_member = False
    async with engine.lock:
        if engine.state not in JOINABLE_STATES:
            raise GameError(GameErrorCode.TEAMS_LOCKED)
        live_team = engine.teams.get(team_id)
        if live_team is None:
            raise GameError(GameErrorCode.TEAM_NOT_FOUND)
        if player_row.team_id == team_id:
            # idempotent - re-joining your own team is not an error
            already_member = True
        elif engine.is_team_full(team_id):
            raise GameError(
                GameErrorCode.TEAM_FULL,
                f"'{live_team.name}' already has {settings.max_team_size} players.",
                details={"teamId": team_id, "maxSize": settings.max_team_size},
            )
        else:
            # persist first: if the write fails, memory is left untouched
            player_row.team_id = team_id
            await session.commit()
            engine.apply_team_assignment(player_row.id, team_id)

    team = await session.get(Team, team_id)
    if team is None:  # pragma: no cover - defensive
        raise GameError(GameErrorCode.TEAM_NOT_FOUND)
    if not already_member:
        await session.refresh(player_row)
        if previous_team_id and previous_team_id != team_id:
            await engine.notify_team_updated(previous_team_id)
        await engine.broadcast_lobby_state(
            WSEventType.TEAM_JOINED,
            {
                "team": {"team_id": team.id, "name": team.name},
                "player": player_out(player_row, team_name=team.name),
            },
        )
    return team


async def create_team(
    session: AsyncSession,
    *,
    pin: str,
    name: str,
    player_id: int | None = None,
    join: bool = True,
) -> Team:
    """Create a team, optionally seating its creator immediately."""
    engine = await get_engine(session, pin)
    if engine.mode != "team":
        raise GameError(
            GameErrorCode.TEAM_MODE_REQUIRED,
            "This game is not running in team mode.",
        )
    if engine.state not in JOINABLE_STATES:
        raise GameError(GameErrorCode.TEAMS_LOCKED)

    cleaned = " ".join((name or "").split())
    if not (
        settings.team_name_min_length
        <= len(cleaned)
        <= settings.team_name_max_length
    ):
        raise GameError(
            GameErrorCode.INVALID_TEAM_NAME,
            f"Team name must be {settings.team_name_min_length}-"
            f"{settings.team_name_max_length} characters.",
        )
    duplicate = await session.scalar(
        select(Team.id).where(
            Team.game_id == engine.id, func.lower(Team.name) == cleaned.lower()
        )
    )
    if duplicate is not None:
        raise GameError(GameErrorCode.TEAM_NAME_TAKEN)

    player_row: Player | None = None
    if player_id is not None:
        player_row = await session.get(Player, player_id)
        if player_row is None or player_row.game_id != engine.id:
            raise GameError(GameErrorCode.PLAYER_NOT_IN_GAME)

    team = Team(game_id=engine.id, name=cleaned)
    session.add(team)
    try:
        await session.commit()
    except IntegrityError as exc:  # unique (game_id, name)
        await session.rollback()
        raise GameError(GameErrorCode.TEAM_NAME_TAKEN) from exc
    await session.refresh(team)

    await engine.register_team(team)
    if join and player_row is not None:
        await assign_player_to_team(
            session, engine=engine, player_row=player_row, team_id=team.id
        )
    return team


async def leave_team(session: AsyncSession, *, pin: str, player_id: int) -> None:
    engine = await get_engine(session, pin)
    if engine.mode != "team":
        raise GameError(GameErrorCode.TEAM_MODE_REQUIRED)
    if engine.state not in JOINABLE_STATES:
        raise GameError(GameErrorCode.TEAMS_LOCKED)

    player_row = await session.get(Player, player_id)
    if player_row is None or player_row.game_id != engine.id:
        raise GameError(GameErrorCode.PLAYER_NOT_IN_GAME)
    if player_row.team_id is None:
        raise GameError(GameErrorCode.NOT_IN_TEAM)

    previous_team_id = player_row.team_id
    async with engine.lock:
        player_row.team_id = None
        await session.commit()
        engine.apply_team_assignment(player_row.id, None)

    await engine.broadcast_lobby_state(
        WSEventType.TEAM_LEFT,
        {"teamId": previous_team_id, "player": player_out(player_row)},
    )
    await engine.notify_team_updated(previous_team_id)


# ------------------------------------------------------------------- helpers
async def require_player(
    session: AsyncSession, *, player_token: str
) -> tuple[Player, GameEngine]:
    """Resolve a player token into a player row + live engine.

    Player tokens are the only credential a participant has; they are verified
    on every call and the player is always re-checked against the game.
    """
    from app.core.security import TOKEN_TYPE_PLAYER, decode_token

    payload = decode_token(player_token, expected_type=TOKEN_TYPE_PLAYER)
    if payload is None:
        raise GameError(GameErrorCode.UNAUTHORIZED, "Invalid or expired player token.")
    try:
        player_id = int(payload["sub"])
        game_id = int(payload["gid"])
        pin = str(payload["pin"])
    except (KeyError, TypeError, ValueError):
        raise GameError(GameErrorCode.UNAUTHORIZED, "Malformed player token.") from None

    player = await session.get(Player, player_id)
    if player is None or player.game_id != game_id:
        raise GameError(GameErrorCode.PLAYER_NOT_IN_GAME)
    engine = await get_engine(session, pin)
    if engine.id != game_id:
        raise GameError(GameErrorCode.PLAYER_NOT_IN_GAME)
    return player, engine


async def lobby_snapshot(session: AsyncSession, engine: GameEngine) -> dict:
    game = await session.get(GameSession, engine.id)
    players = (
        await session.scalars(
            select(Player).where(Player.game_id == engine.id).order_by(Player.joined_at, Player.id)
        )
    ).all()
    teams = (
        await session.scalars(
            select(Team).where(Team.game_id == engine.id).order_by(Team.created_at, Team.id)
        )
    ).all()
    names = {t.id: t.name for t in teams}
    return {
        "game": game_lookup_out(game, engine),
        "players": [
            player_out(p, team_name=names.get(p.team_id)) for p in players
        ],
        "teams": [team_out(t, list(players)) for t in teams],
    }
    await session.refresh(game)
    logger.info("game %s created for quiz %s by user %s", game.game_pin, quiz_id, host.id)
    return game


async def get_game_by_pin(session: AsyncSession, pin: str) -> GameSession:
    normalised = normalise_pin(pin)
    game = await session.scalar(
        select(GameSession).where(GameSession.game_pin == normalised)
    )
    if game is None:
        raise GameError(GameErrorCode.GAME_NOT_FOUND)
    return game


async def get_engine(session: AsyncSession, pin: str) -> GameEngine:
    return await get_registry().get(normalise_pin(pin))