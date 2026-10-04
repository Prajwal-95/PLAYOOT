"""Shared pytest fixtures.

Design rules for this suite:

* **Never touch the real database.** A throwaway SQLite file in a temp dir is
  created per session and the app's engine/session factory are re-pointed at it.
* **Never spend Groq credits.** ``GROQ_API_KEY`` is a dummy and every AI test
  monkeypatches the generator factory with a fake.
* **Never leak limiter state.** Limits are off by default; each test starts
  with an empty limiter.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ---------------------------------------------------------------- environment
# These MUST be set before `app.config` is imported: pydantic-settings gives the
# real environment priority over backend/.env.
_TMP_DIR = tempfile.mkdtemp(prefix="playoot-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(Path(_TMP_DIR) / 'test.db').as_posix()}"
os.environ["AUTO_MIGRATE"] = "false"
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-only-secret-not-used-anywhere-real"
os.environ["GROQ_API_KEY"] = "test-key-never-sent"
os.environ["GROQ_MAX_ATTEMPTS"] = "1"
os.environ["GROQ_RETRY_BASE_DELAY"] = "0"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["RATE_LIMIT_TRUST_PROXY"] = "false"

import pytest  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import app.database as database  # noqa: E402
import app.game.registry as registry_module  # noqa: E402
from app.core.ratelimit import limiter  # noqa: E402
from app.database import Base  # noqa: E402
from app.game.manager import manager  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402

# Register every model on the metadata before create_all.
import app.models.game  # noqa: E402,F401
import app.models.quiz  # noqa: E402,F401
import app.models.user  # noqa: E402,F401

# NullPool: connections are never reused across event loops, so the synchronous
# TestClient and the asyncio engine tests can share this one engine.
test_engine = create_async_engine(
    os.environ["DATABASE_URL"], poolclass=NullPool, future=True
)
TestSession = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)

# Re-point every module that captured the factory at import time.
database.engine = test_engine
database.SessionLocal = TestSession
registry_module.SessionLocal = TestSession

VALID_PASSWORD = "SuperSecret123"


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    import asyncio

    async def _create() -> None:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    yield
    asyncio.run(test_engine.dispose())
    shutil.rmtree(_TMP_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_global_state():
    """Every test starts with no rate-limit counters and no live engines.

    The connection manager is reset too: it holds an ``asyncio.Lock`` that binds
    to the first loop that awaits it, and this suite mixes Starlette's
    ``TestClient`` (its own portal loop) with pytest-asyncio tests (the pytest
    loop). A fresh lock lets each test bind to its own loop.
    """
    _reset_singletons()
    yield
    registry = registry_module.get_registry()
    for pin in registry.loaded_pins():  # cancel authoritative timers
        engine = registry.peek(pin)
        if engine is not None:
            engine._cancel_timer()
    _reset_singletons()


def _reset_singletons() -> None:
    import asyncio as _asyncio

    limiter.reset()
    registry_module.reset_registry()
    manager._rooms.clear()
    manager._players.clear()
    manager._lock = _asyncio.Lock()


@pytest.fixture
def client():
    test_client = TestClient(fastapi_app)
    test_client.__enter__()
    try:
        yield test_client
    finally:
        # Drop any engines first: the lifespan shutdown cancels their timers, and
        # a timer created on another loop cannot be cancelled from this one.
        _reset_singletons()
        test_client.__exit__(None, None, None)


def _register(client, prefix: str) -> dict:
    email = f"{prefix}_{uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/auth/register",
        json={"name": "Test User", "email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return {
        "email": email,
        "password": VALID_PASSWORD,
        "token": token,
        "user": response.json()["user"],
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def host(client) -> dict:
    """A registered host account with a valid bearer header."""
    return _register(client, "host")


@pytest.fixture
def other_host(client) -> dict:
    """A second account, used for authorisation checks."""
    return _register(client, "other")


def question(text: str, options: list[str], correct: str, points: int = 1000) -> dict:
    return {
        "question_text": text,
        "question_type": "multiple_choice",
        "options": options,
        "correct_answer": correct,
        "explanation": f"The answer is {correct}.",
        "time_limit": 5,
        "points": points,
    }


@pytest.fixture
def quiz(client, host) -> dict:
    """A two-question quiz owned by ``host`` (index 0 is always correct)."""
    response = client.post(
        "/api/quizzes",
        headers=host["headers"],
        json={
            "title": "Smoke Quiz",
            "description": "created by the test suite",
            "source_type": "manual",
            "questions": [
                question("Capital of France?", ["Paris", "Rome", "Berlin", "Madrid"], "Paris"),
                question("2 + 2 = ?", ["3", "4", "5", "6"], "4"),
            ],
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


@pytest.fixture
def game(client, host, quiz) -> dict:
    """A lobby game created from ``quiz``."""
    response = client.post(
        "/api/games",
        headers=host["headers"],
        json={"quiz_id": quiz["id"], "mode": "individual"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def join(client, game: dict, nickname: str) -> dict:
    response = client.post(
        f"/api/games/{game['game_pin']}/join", json={"nickname": nickname}
    )
    assert response.status_code == 201, response.text
    return response.json()