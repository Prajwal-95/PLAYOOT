"""Timezone-safe datetime helpers.

SQLite silently drops ``tzinfo`` when persisting ``DateTime(timezone=True)``
columns, so every datetime that comes back out of the database must be
normalised through :func:`as_utc` before it is used in arithmetic.  Doing this
in one place removes an entire class of "can't subtract offset-naive and
offset-aware datetimes" bugs from the game engine.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    """Current time as an aware UTC datetime."""
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """Return ``value`` as an aware UTC datetime (``None`` passes through)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso(value: datetime | None) -> str | None:
    """ISO-8601 representation safe to put on the wire."""
    normalised = as_utc(value)
    return normalised.isoformat() if normalised else None


def epoch_ms(value: datetime | None) -> int | None:
    """Unix epoch milliseconds - convenient for client-side countdowns."""
    normalised = as_utc(value)
    return int(normalised.timestamp() * 1000) if normalised else None


def ms_between(start: datetime, end: datetime) -> int:
    """Milliseconds elapsed between two (possibly naive) datetimes."""
    a, b = as_utc(start), as_utc(end)
    return int((b - a).total_seconds() * 1000)


def plus_seconds(base: datetime, seconds: float) -> datetime:
    return as_utc(base) + timedelta(seconds=seconds)