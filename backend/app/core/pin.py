"""Server-side game PIN generation.

Rules enforced here:

* digits only, fixed length (default 6) - easy to type on a phone keypad
* generated exclusively on the server; no client-supplied PIN is ever trusted
* globally unique - the ``players``/``game_sessions`` schema enforces it with a
  unique index and this helper retries on collision
"""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.game.errors import GameError, GameErrorCode
from app.models.game import GameSession

_PIN_ALPHABET = "0123456789"
_MAX_ATTEMPTS = 40


def normalise_pin(raw: str | None) -> str:
    """Strip whitespace/formatting and validate the shape of a user-entered PIN."""
    candidate = "".join(ch for ch in (raw or "").strip() if ch.isdigit())
    if len(candidate) != settings.game_pin_length:
        raise GameError(
            GameErrorCode.INVALID_PIN,
            f"A game PIN is {settings.game_pin_length} digits.",
        )
    return candidate


def _random_pin() -> str:
    return "".join(secrets.choice(_PIN_ALPHABET) for _ in range(settings.game_pin_length))


async def generate_unique_pin(session: AsyncSession) -> str:
    """Return a PIN not used by *any* existing game session."""
    for _ in range(_MAX_ATTEMPTS):
        candidate = _random_pin()
        existing = await session.scalar(
            select(GameSession.id).where(GameSession.game_pin == candidate).limit(1)
        )
        if existing is None:
            return candidate
    raise GameError(
        GameErrorCode.INTERNAL_ERROR,
        "Could not allocate a unique game PIN, please try again.",
        status_code=503,
    )