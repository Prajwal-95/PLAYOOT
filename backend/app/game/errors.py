"""Typed, user-presentable game errors.

Every failure path in the engine raises a :class:`GameError` carrying a stable
machine-readable ``code``.  The WebSocket layer converts it into a
``GAME_ERROR`` event and the REST layer into an HTTP error response, so the
frontend never has to guess what went wrong and nothing fails silently.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class GameErrorCode(str, Enum):
    # --- lookup / lifecycle ------------------------------------------------
    INVALID_PIN = "INVALID_PIN"
    GAME_NOT_FOUND = "GAME_NOT_FOUND"
    GAME_ALREADY_STARTED = "GAME_ALREADY_STARTED"
    GAME_NOT_JOINABLE = "GAME_NOT_JOINABLE"
    GAME_FULL = "GAME_FULL"
    GAME_ENDED = "GAME_ENDED"
    GAME_CANCELLED = "GAME_CANCELLED"
    GAME_NOT_ACTIVE = "GAME_NOT_ACTIVE"
    GAME_ALREADY_ACTIVE = "GAME_ALREADY_ACTIVE"
    NO_QUESTIONS = "NO_QUESTIONS"
    NO_PLAYERS = "NO_PLAYERS"

    # --- players -----------------------------------------------------------
    PLAYER_NOT_IN_GAME = "PLAYER_NOT_IN_GAME"
    INVALID_NICKNAME = "INVALID_NICKNAME"
    NICKNAME_TAKEN = "NICKNAME_TAKEN"
    PLAYER_NOT_CONNECTED = "PLAYER_NOT_CONNECTED"

    # --- teams -------------------------------------------------------------
    TEAM_MODE_REQUIRED = "TEAM_MODE_REQUIRED"
    TEAM_NOT_FOUND = "TEAM_NOT_FOUND"
    TEAM_FULL = "TEAM_FULL"
    TEAM_NAME_TAKEN = "TEAM_NAME_TAKEN"
    INVALID_TEAM_NAME = "INVALID_TEAM_NAME"
    ALREADY_IN_TEAM = "ALREADY_IN_TEAM"
    NOT_IN_TEAM = "NOT_IN_TEAM"
    TEAMS_LOCKED = "TEAMS_LOCKED"

    # --- questions / answers ----------------------------------------------
    NO_ACTIVE_QUESTION = "NO_ACTIVE_QUESTION"
    QUESTION_MISMATCH = "QUESTION_MISMATCH"
    QUESTION_EXPIRED = "QUESTION_EXPIRED"
    ALREADY_ANSWERED = "ALREADY_ANSWERED"
    INVALID_ANSWER = "INVALID_ANSWER"

    # --- authorization / protocol -----------------------------------------
    UNAUTHORIZED_HOST = "UNAUTHORIZED_HOST"
    UNAUTHORIZED = "UNAUTHORIZED"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    BAD_REQUEST = "BAD_REQUEST"
    INTERNAL_ERROR = "INTERNAL_ERROR"


#: Sensible HTTP status codes for the codes that can surface over REST.
DEFAULT_HTTP_STATUS: dict[GameErrorCode, int] = {
    GameErrorCode.INVALID_PIN: 400,
    GameErrorCode.GAME_NOT_FOUND: 404,
    GameErrorCode.GAME_ALREADY_STARTED: 409,
    GameErrorCode.GAME_NOT_JOINABLE: 409,
    GameErrorCode.GAME_FULL: 409,
    GameErrorCode.GAME_ENDED: 409,
    GameErrorCode.GAME_CANCELLED: 409,
    GameErrorCode.GAME_NOT_ACTIVE: 409,
    GameErrorCode.GAME_ALREADY_ACTIVE: 409,
    GameErrorCode.NO_QUESTIONS: 400,
    GameErrorCode.NO_PLAYERS: 400,
    GameErrorCode.PLAYER_NOT_IN_GAME: 403,
    GameErrorCode.UNAUTHORIZED: 401,
    GameErrorCode.UNAUTHORIZED_HOST: 403,
    GameErrorCode.TEAM_FULL: 409,
    GameErrorCode.TEAM_NAME_TAKEN: 409,
    GameErrorCode.NICKNAME_TAKEN: 409,
    GameErrorCode.INVALID_NICKNAME: 422,
    GameErrorCode.INVALID_TEAM_NAME: 422,
    GameErrorCode.TEAM_NOT_FOUND: 404,
    GameErrorCode.BAD_REQUEST: 400,
    GameErrorCode.INVALID_ANSWER: 422,
    GameErrorCode.ALREADY_ANSWERED: 409,
    GameErrorCode.QUESTION_EXPIRED: 409,
    GameErrorCode.INTERNAL_ERROR: 500,
}

#: Human-readable fallbacks; the engine passes a more specific message when it
#: has one.
DEFAULT_MESSAGES: dict[GameErrorCode, str] = {
    GameErrorCode.INVALID_PIN: "That game PIN is not valid.",
    GameErrorCode.GAME_NOT_FOUND: "No game exists with that PIN.",
    GameErrorCode.GAME_ALREADY_STARTED: "This game has already started.",
    GameErrorCode.GAME_NOT_JOINABLE: "This game is no longer accepting players.",
    GameErrorCode.GAME_FULL: "This game is full.",
    GameErrorCode.GAME_ENDED: "This game has ended.",
    GameErrorCode.GAME_CANCELLED: "This game was cancelled by the host.",
    GameErrorCode.GAME_NOT_ACTIVE: "This game is not currently running.",
    GameErrorCode.GAME_ALREADY_ACTIVE: "This game is already running.",
    GameErrorCode.NO_QUESTIONS: "This quiz has no questions.",
    GameErrorCode.NO_PLAYERS: "At least one player must join before the game can start.",
    GameErrorCode.PLAYER_NOT_IN_GAME: "You are not a player in this game.",
    GameErrorCode.INVALID_NICKNAME: "Please choose a different nickname.",
    GameErrorCode.NICKNAME_TAKEN: "That nickname is already taken in this game.",
    GameErrorCode.PLAYER_NOT_CONNECTED: "This player is not connected.",
    GameErrorCode.TEAM_MODE_REQUIRED: "Teams are only available in team mode.",
    GameErrorCode.TEAM_NOT_FOUND: "That team does not exist.",
    GameErrorCode.TEAM_FULL: "That team is full.",
    GameErrorCode.TEAM_NAME_TAKEN: "A team with that name already exists.",
    GameErrorCode.INVALID_TEAM_NAME: "Please choose a different team name.",
    GameErrorCode.ALREADY_IN_TEAM: "You are already on a team.",
    GameErrorCode.NOT_IN_TEAM: "You are not on a team.",
    GameErrorCode.TEAMS_LOCKED: "Teams are locked once the game has started.",
    GameErrorCode.NO_ACTIVE_QUESTION: "There is no active question right now.",
    GameErrorCode.QUESTION_MISMATCH: "That answer was for a different question.",
    GameErrorCode.QUESTION_EXPIRED: "Time ran out for that question.",
    GameErrorCode.ALREADY_ANSWERED: "You have already answered this question.",
    GameErrorCode.INVALID_ANSWER: "That is not a valid answer option.",
    GameErrorCode.UNAUTHORIZED_HOST: "Only the host can do that.",
    GameErrorCode.UNAUTHORIZED: "You are not authorized to do that.",
    GameErrorCode.INVALID_STATE_TRANSITION: "The game is not in a state that allows that.",
    GameErrorCode.BAD_REQUEST: "That request could not be understood.",
    GameErrorCode.INTERNAL_ERROR: "Something went wrong on the server.",
}


class GameError(Exception):
    """Raised for every expected/recoverable game failure."""

    def __init__(
        self,
        code: GameErrorCode | str,
        message: str | None = None,
        *,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = GameErrorCode(code)
        self.message = message or DEFAULT_MESSAGES.get(self.code, "Game error.")
        self.status_code = status_code or DEFAULT_HTTP_STATUS.get(self.code, 400)
        self.details = details or {}
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code.value, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GameError {self.code.value}: {self.message}>"