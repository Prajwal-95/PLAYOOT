"""Rate limiting: 429s, IP isolation, configurability, and no leakage."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.ai.base import GeneratedQuestion, QuizGenerationError
from app.config import settings
from app.core.ratelimit import FixedWindowLimiter
from conftest import VALID_PASSWORD


class _FakeGen:
    @property
    def provider(self) -> str:
        return "fake"

    async def generate(self, request):
        return [
            GeneratedQuestion(
                question_text="Q?",
                question_type="multiple_choice",
                options=["a", "b", "c", "d"],
                correct_answer="a",
                explanation="because",
                time_limit=request.time_limit,
                points=request.points,
            )
        ]


@pytest.fixture
def limited(monkeypatch):
    """Turn limiting on with tiny, predictable budgets."""
    from app.core.ratelimit import limiter

    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_trust_proxy", True)
    monkeypatch.setattr(settings, "auth_rate_window_seconds", 60)
    monkeypatch.setattr(settings, "auth_login_limit", 3)
    monkeypatch.setattr(settings, "auth_register_limit", 3)
    monkeypatch.setattr(settings, "ai_rate_window_seconds", 3600)
    monkeypatch.setattr(settings, "ai_generate_user_limit", 2)
    monkeypatch.setattr(settings, "ai_generate_ip_limit", 1000)
    limiter.reset()
    yield
    limiter.reset()


def _register(client):
    return client.post(
        "/api/auth/register",
        json={
            "name": "U",
            "email": f"rl_{uuid4().hex[:10]}@example.com",
            "password": VALID_PASSWORD,
        },
    )


def _login(client, email="a@b.com", ip: str | None = None):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return client.post(
        "/api/auth/login", json={"email": email, "password": "nope"}, headers=headers
    )


# ------------------------------------------------------------------- auth caps
def test_login_is_capped_per_ip(client, limited):
    codes = [_login(client).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]


def test_login_429_shape_is_safe(client, limited):
    for _ in range(4):
        response = _login(client)
    assert response.status_code == 429
    detail = response.json()["detail"]
    assert detail["code"] == "RATE_LIMITED"
    assert "too many" in detail["message"].lower()
    assert int(response.headers["Retry-After"]) > 0
    for banned in ("traceback", "groq", "gsk_", "sqlalchemy", "sqlite"):
        assert banned not in response.text.lower()


def test_register_is_capped_per_ip(client, limited):
    codes = [_register(client).status_code for _ in range(6)]
    assert codes[:3] == [201, 201, 201]
    assert all(code == 429 for code in codes[3:])


def test_buckets_are_independent(client, limited):
    """Burning the login budget must not block registration."""
    for _ in range(4):
        _login(client)
    assert _register(client).status_code == 201


def test_forwarded_for_separates_clients(client, limited):
    for _ in range(4):
        _login(client, ip="203.0.113.1")
    assert _login(client, ip="203.0.113.1").status_code == 429
    # a different client address has its own budget
    assert _login(client, ip="203.0.113.2").status_code == 401


def test_real_correct_login_still_works_under_limit(client, limited, host):
    response = client.post(
        "/api/auth/login", json={"email": host["email"], "password": host["password"]}
    )
    assert response.status_code == 200


# ------------------------------------------------------------------- ai caps
def test_ai_generation_is_capped_per_user(client, limited, host, monkeypatch):
    import app.api.routes_quiz as routes_quiz

    monkeypatch.setattr(routes_quiz, "get_quiz_generator", lambda: _FakeGen())
    payload = {
        "source_type": "topic",
        "topic": "x",
        "question_count": 1,
        "save": False,
    }
    codes = [
        client.post("/api/quizzes/generate", headers=host["headers"], json=payload).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]


def test_ai_cap_does_not_block_normal_reads(client, limited, host):
    assert client.get("/api/quizzes", headers=host["headers"]).status_code == 200
    assert client.get("/api/health").status_code == 200


# ------------------------------------------------------------------- disabled
def test_limits_are_skipped_when_disabled(client, monkeypatch):
    from app.core.ratelimit import limiter

    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(settings, "auth_login_limit", 1)
    limiter.reset()
    codes = [_login(client).status_code for _ in range(5)]
    assert 429 not in codes


# ------------------------------------------------------------ limiter itself
async def test_limiter_allows_up_to_the_limit_then_blocks():
    limiter = FixedWindowLimiter()
    for _ in range(3):
        assert (await limiter.hit("b", "s", 3, 60)).allowed is True
    decision = await limiter.hit("b", "s", 3, 60)
    assert decision.allowed is False
    assert decision.remaining == 0
    assert decision.retry_after > 0


async def test_limiter_keys_are_isolated():
    limiter = FixedWindowLimiter()
    await limiter.hit("b", "one", 1, 60)
    assert (await limiter.hit("b", "one", 1, 60)).allowed is False
    assert (await limiter.hit("b", "two", 1, 60)).allowed is True
    assert (await limiter.hit("other", "one", 1, 60)).allowed is True


async def test_limiter_zero_limit_disables_bucket():
    limiter = FixedWindowLimiter()
    for _ in range(5):
        assert (await limiter.hit("b", "s", 0, 60)).allowed is True


async def test_limiter_window_expires():
    limiter = FixedWindowLimiter()
    assert (await limiter.hit("b", "s", 1, 60)).allowed is True
    assert (await limiter.hit("b", "s", 1, 60)).allowed is False
    await asyncio.sleep(0)
    limiter._hits[("b", "s")] = (0.0, 5, 0)  # pretend the window already elapsed
    assert (await limiter.hit("b", "s", 1, 60)).allowed is True


# ----------------------------------------------- errors vs throttling
def test_generation_failure_is_not_reported_as_rate_limited(client, host, monkeypatch):
    """A provider outage must surface as 502, never as 429."""

    class _Boom(_FakeGen):
        async def generate(self, request):
            raise QuizGenerationError("upstream exploded", code="AI_PROVIDER_ERROR")

    import app.api.routes_quiz as routes_quiz

    monkeypatch.setattr(routes_quiz, "get_quiz_generator", lambda: _Boom())
    response = client.post(
        "/api/quizzes/generate",
        headers=host["headers"],
        json={"source_type": "topic", "topic": "x", "question_count": 1, "save": False},
    )
    assert response.status_code == 502
    assert "upstream exploded" not in response.text