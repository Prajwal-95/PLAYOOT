"""Production configuration guard rails.

These assert the app refuses to boot with development settings, and accepts a
correctly configured production environment.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import ProductionConfigError, Settings


def prod(**overrides) -> dict:
    """A valid production baseline; tests break one thing at a time."""
    base = dict(
        environment="production",
        debug=False,
        auto_migrate=False,
        database_url="postgresql+asyncpg://user:pass@db:5432/playoot",
        secret_key="a-strong-unique-production-secret-key-value-0123456789",
        cors_origins="https://playoot.example.com",
        groq_api_key="gsk_fake",
        google_client_id=None,
        google_client_secret=None,
        google_redirect_uri="",
        firebase_project_id=None,
    )
    base.update(overrides)
    return base


def test_valid_production_config_is_accepted():
    settings = Settings(**prod())
    assert settings.is_production is True
    assert settings.is_postgres is True
    assert settings.debug is False
    assert settings.auto_migrate is False


def test_derived_properties():
    settings = Settings(**prod())
    assert settings.cors_origin_list == ["https://playoot.example.com"]
    assert settings.sync_database_url.startswith("postgresql+psycopg2://")


def test_multiple_production_origins_are_supported():
    settings = Settings(
        **prod(cors_origins="https://a.example.com, https://b.example.com")
    )
    assert settings.cors_origin_list == ["https://a.example.com", "https://b.example.com"]


# ------------------------------------------------------------------ refusals
@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"database_url": "sqlite+aiosqlite:///./quizhost.db"}, "PostgreSQL"),
        ({"debug": True}, "DEBUG"),
        ({"auto_migrate": True}, "AUTO_MIGRATE"),
        ({"secret_key": "dev-insecure-secret-change-me"}, "SECRET_KEY"),
        ({"secret_key": "short"}, "SECRET_KEY"),
        ({"cors_origins": "*"}, "CORS_ORIGINS"),
        ({"cors_origins": "http://localhost:5173"}, "CORS_ORIGINS"),
        ({"cors_origins": "http://127.0.0.1:5173"}, "CORS_ORIGINS"),
        ({"cors_origins": ""}, "CORS_ORIGINS"),
        ({"groq_api_key": None}, "GROQ_API_KEY"),
        (
            {
                "google_client_id": "abc.apps.googleusercontent.com",
                "google_redirect_uri": "http://localhost:8000/api/auth/google/callback",
            },
            "GOOGLE_REDIRECT_URI",
        ),
    ],
)
def test_production_refuses_development_settings(overrides, expected):
    with pytest.raises((ProductionConfigError, ValidationError)) as excinfo:
        Settings(**prod(**overrides))
    assert expected in str(excinfo.value)


def test_ai_can_be_disabled_without_a_groq_key():
    settings = Settings(**prod(ai_enabled=False, groq_api_key=None))
    assert settings.ai_enabled is False


def test_production_error_lists_every_problem_at_once():
    with pytest.raises((ProductionConfigError, ValidationError)) as excinfo:
        Settings(**prod(database_url="sqlite+aiosqlite:///./x.db", debug=True))
    message = str(excinfo.value)
    assert "PostgreSQL" in message
    assert "DEBUG" in message


# ------------------------------------------------------- development is fine
def test_development_defaults_are_not_validated():
    """Local dev keeps SQLite + localhost + debug."""
    settings = Settings(
        environment="development",
        debug=True,
        auto_migrate=True,
        database_url="sqlite+aiosqlite:///./quizhost.db",
        secret_key="dev-insecure-secret-change-me",
        cors_origins="http://localhost:5173,http://127.0.0.1:5173",
        groq_api_key=None,
    )
    assert settings.is_production is False
    assert settings.is_sqlite is True
    assert "http://localhost:5173" in settings.cors_origin_list


def test_test_environment_is_not_production():
    from app.config import settings as active

    assert active.is_production is False