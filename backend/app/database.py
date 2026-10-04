"""Async SQLAlchemy engine / session plumbing.

The URL in ``settings.database_url`` decides the backend:

* ``postgresql+asyncpg://...``  - production target
* ``sqlite+aiosqlite:///...``   - zero-setup local development

Models deliberately stick to portable column types (``String``, ``Integer``,
``Boolean``, ``DateTime(timezone=True)``, ``Text``, ``JSON``) so one Alembic
migration works against both engines.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


def _engine_options() -> dict:
    """Engine keyword arguments tuned for the active backend.

    PostgreSQL needs an explicit bounded pool: the default can open more
    connections than the server's ``max_connections`` allows once several
    workers are involved. ``pool_pre_ping`` plus ``pool_recycle`` keeps long
    lived connections healthy through proxies/firewalls that drop idle TCP.
    """
    options: dict = {
        "echo": settings.db_echo,
        "future": True,
        "pool_pre_ping": not settings.is_sqlite,
    }
    if settings.is_postgres:
        options.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle,
        )
    return options


engine = create_async_engine(settings.database_url, **_engine_options())

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


if settings.is_sqlite:

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):  # pragma: no cover
        """WAL + a generous busy timeout keeps concurrent WS writes from
        raising 'database is locked' during a live game."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a short-lived session per request."""
    async with SessionLocal() as session:
        yield session


async def dispose_engine() -> None:
    await engine.dispose()