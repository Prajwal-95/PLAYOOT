"""In-process fixed-window rate limiting.

No third-party dependency on purpose: the game engine already keeps state in
this process, so a single-process deployment needs nothing more. Swap
:class:`FixedWindowLimiter` for a Redis-backed implementation when running
more than one instance.

Counters are keyed by ``(bucket, subject)`` where *subject* is either an IP or
a user id, so the same policy can be enforced per-IP for anonymous traffic and
per-account for authenticated traffic.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    """Outcome of a single limiter check."""

    allowed: bool
    limit: int
    remaining: int
    retry_after: int  # seconds; 0 when allowed


class FixedWindowLimiter:
    """Thread/async-safe fixed-window counter with lazy eviction.

    A fixed window is deliberate: it is O(1), allocation-cheap and good enough
    to stop credential stuffing and runaway AI spend, which are the two things
    this actually protects.
    """

    def __init__(self) -> None:
        # (bucket, subject) -> (window_start, count, window_seconds)
        self._hits: dict[tuple[str, str], tuple[float, int, int]] = {}
        self._lock = asyncio.Lock()
        self._last_sweep = 0.0

    async def hit(self, bucket: str, subject: str, limit: int, window: int) -> Decision:
        """Register one call against ``bucket``/``subject``."""
        if limit <= 0 or window <= 0:
            # A non-positive limit disables the bucket without special-casing
            # it at every call site.
            return Decision(True, 0, 0, 0)

        now = time.monotonic()
        async with self._lock:
            if now - self._last_sweep > 30:
                self._last_sweep = now
                self._sweep(now)

            key = (bucket, subject)
            start, count, win = self._hits.get(key, (now, 0, window))
            if now - start >= win:
                start, count, win = now, 0, window

            count += 1
            self._hits[key] = (start, count, win)

            if count > limit:
                retry_after = max(1, int(win - (now - start)) + 1)
                return Decision(False, limit, 0, retry_after)
            return Decision(True, limit, limit - count, 0)

    def _sweep(self, now: float) -> None:
        """Drop windows that finished long ago. Amortised, so this is cheap."""
        stale = [
            key
            for key, (start, _count, win) in self._hits.items()
            if now - start > win * 2
        ]
        for key in stale:
            self._hits.pop(key, None)

    def peek(self, bucket: str, subject: str, limit: int, window: int) -> Decision:
        """Inspect without consuming a slot (used by tests)."""
        start, count, _win = self._hits.get((bucket, subject), (0.0, 0, window))
        now = time.monotonic()
        if start == 0.0 or now - start >= window:
            return Decision(True, limit, limit, 0)
        if count > limit:
            return Decision(False, limit, 0, max(1, int(window - (now - start)) + 1))
        return Decision(True, limit, limit - count, 0)

    def reset(self) -> None:
        """Clear every counter (tests only)."""
        self._hits.clear()


#: Process-wide singleton shared by the API dependencies.
limiter = FixedWindowLimiter()