"""Process-wide registry of live game engines.

One engine per game PIN.  Engines are created lazily from persisted state the
first time a socket attaches, and can be dropped once a game reaches a terminal
state.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import SessionLocal
from app.game.engine import GameEngine
from app.game.errors import GameError, GameErrorCode
from app.game.manager import ConnectionManager, manager as default_manager

logger = logging.getLogger(__name__)


class GameRegistry:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        connection_manager: ConnectionManager | None = None,
    ) -> None:
        self._session_factory = session_factory or SessionLocal
        self._manager = connection_manager or default_manager
        self._engines: dict[str, GameEngine] = {}
        self._lock = asyncio.Lock()

    # -------------------------------------------------------------- lookup
    def peek(self, pin: str) -> GameEngine | None:
        """Return an already-loaded engine without touching the database."""
        return self._engines.get(pin)

    def loaded_pins(self) -> list[str]:
        return list(self._engines)

    async def get(self, pin: str) -> GameEngine:
        """Return the live engine for ``pin``, hydrating it if necessary."""
        engine = self._engines.get(pin)
        if engine is not None:
            return engine
        async with self._lock:
            engine = self._engines.get(pin)
            if engine is not None:
                return engine
            async with self._session_factory() as session:
                engine = await GameEngine.load(
                    self._session_factory,
                    session,
                    pin,
                    connection_manager=self._manager,
                )
            self._engines[pin] = engine
            logger.info("hydrated game engine for pin %s", pin)
        # re-arm the authoritative timer (or close an expired question)
        await engine.resume_timer_if_needed()
        return engine

    async def get_or_none(self, pin: str) -> GameEngine | None:
        try:
            return await self.get(pin)
        except GameError as exc:
            if exc.code == GameErrorCode.GAME_NOT_FOUND:
                return None
            raise

    # ----------------------------------------------------------- lifecycle
    async def drop(self, pin: str) -> None:
        async with self._lock:
            engine = self._engines.pop(pin, None)
        if engine is not None:
            engine._cancel_timer()

    async def shutdown(self) -> None:
        async with self._lock:
            engines = list(self._engines.values())
            self._engines.clear()
        for engine in engines:
            engine._cancel_timer()
        logger.info("game registry shut down (%d engines)", len(engines))


_registry: GameRegistry | None = None


def get_registry() -> GameRegistry:
    """Lazily-created process singleton (safe to call from any module)."""
    global _registry
    if _registry is None:
        _registry = GameRegistry()
    return _registry


def reset_registry() -> None:
    """Test helper: forget all live engines."""
    global _registry
    _registry = None