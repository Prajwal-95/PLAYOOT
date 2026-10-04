"""Single source of truth for the WebSocket vocabulary.

Both directions of traffic are declared here so a frontend typo or a
server-side rename can never drift out of sync silently.

Wire format (every message, both directions)::

    {
      "type": "QUESTION_STARTED",
      "timestamp": "2026-01-01T12:00:00+00:00",
      "payload": { ... }
    }
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from app.core.timeutil import iso, utcnow


class WSEventType(str, Enum):
    """Server -> client events."""

    CONNECTED = "CONNECTED"
    STATE_SYNC = "STATE_SYNC"
    PONG = "PONG"

    PLAYER_JOINED = "PLAYER_JOINED"
    PLAYER_LEFT = "PLAYER_LEFT"
    PLAYER_UPDATED = "PLAYER_UPDATED"

    TEAM_CREATED = "TEAM_CREATED"
    TEAM_JOINED = "TEAM_JOINED"
    TEAM_LEFT = "TEAM_LEFT"
    TEAM_UPDATED = "TEAM_UPDATED"

    GAME_STARTED = "GAME_STARTED"
    GAME_FINISHED = "GAME_FINISHED"
    GAME_CANCELLED = "GAME_CANCELLED"
    GAME_ERROR = "GAME_ERROR"

    QUESTION_STARTED = "QUESTION_STARTED"
    ANSWER_SUBMITTED = "ANSWER_SUBMITTED"
    PLAYER_ANSWERED = "PLAYER_ANSWERED"
    QUESTION_ENDED = "QUESTION_ENDED"
    NEXT_QUESTION = "NEXT_QUESTION"

    LEADERBOARD_UPDATED = "LEADERBOARD_UPDATED"


class WSClientAction(str, Enum):
    """Client -> server actions."""

    # host only ---------------------------------------------------------
    START_GAME = "START_GAME"
    NEXT_QUESTION = "NEXT_QUESTION"
    END_QUESTION = "END_QUESTION"
    END_GAME = "END_GAME"
    CANCEL_GAME = "CANCEL_GAME"

    # player only -------------------------------------------------------
    SUBMIT_ANSWER = "SUBMIT_ANSWER"

    # any ---------------------------------------------------------------
    REQUEST_STATE = "REQUEST_STATE"
    PING = "PING"


HOST_ACTIONS: frozenset[WSClientAction] = frozenset(
    {
        WSClientAction.START_GAME,
        WSClientAction.NEXT_QUESTION,
        WSClientAction.END_QUESTION,
        WSClientAction.END_GAME,
        WSClientAction.CANCEL_GAME,
    }
)

PLAYER_ACTIONS: frozenset[WSClientAction] = frozenset({WSClientAction.SUBMIT_ANSWER})


def envelope(event_type: WSEventType | str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wrap ``payload`` in the canonical envelope."""
    return {
        "type": event_type.value if isinstance(event_type, Enum) else str(event_type),
        "timestamp": iso(utcnow()),
        "payload": payload or {},
    }


def parse_client_message(raw: Any) -> tuple[WSClientAction, dict[str, Any]]:
    """Validate an inbound frame.

    Raises ``ValueError`` for anything malformed so the caller can answer with
    a ``GAME_ERROR`` instead of crashing the connection handler.
    """
    if not isinstance(raw, dict):
        raise ValueError("Message must be a JSON object.")
    raw_type = raw.get("type")
    if not isinstance(raw_type, str):
        raise ValueError("Message is missing a string 'type'.")
    try:
        action = WSClientAction(raw_type.strip().upper())
    except ValueError as exc:
        raise ValueError(f"Unknown action '{raw_type}'.") from exc
    payload = raw.get("payload") or {}
    if not isinstance(payload, dict):
        raise ValueError("'payload' must be a JSON object.")
    return action, payload