"""Centralised, environment-driven configuration.

Nothing in this module is ever sent to the client.  In particular the
``groq_api_key`` and ``secret_key`` values stay server-side only.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

#: Secret values that are placeholders and must never reach production.
_PLACEHOLDER_SECRETS = {
    "dev-insecure-secret-change-me",
    "dev-insecure-secret-change-me-in-production",
    "changeme",
    "change-me",
    "secret",
}

#: Origins that are never acceptable in production.
_LOCAL_HOST_MARKERS = ("localhost", "127.0.0.1", "0.0.0.0", "[::1]")


class ProductionConfigError(RuntimeError):
    """Raised at start-up when ``ENVIRONMENT=production`` is misconfigured.

    Failing here is deliberate: a half-configured production box must refuse to
    boot rather than silently fall back to development defaults.
    """


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ app
    app_name: str = "PLAYOOT IN EVERYWHERE"
    environment: str = "development"
    debug: bool = True

    # ------------------------------------------------------------ database
    # Production : postgresql+asyncpg://user:pass@host:5432/quizhost
    # Local dev  : sqlite+aiosqlite:///./quizhost.db
    database_url: str = "sqlite+aiosqlite:///./quizhost.db"
    db_echo: bool = False
    #: PostgreSQL connection pool (ignored for SQLite)
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800
    #: run ``alembic upgrade head`` on startup (handy in dev, MUST be false in
    #: production - there it is an explicit deploy step instead)
    auto_migrate: bool = False

    # ---------------------------------------------------------------- auth
    secret_key: str = "dev-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # ---------------------------------------------------------------- game
    game_pin_length: int = 6
    max_team_size: int = 4
    max_players_per_game: int = 500
    nickname_min_length: int = 2
    nickname_max_length: int = 20
    team_name_min_length: int = 2
    team_name_max_length: int = 24
    # milliseconds of slack added to the authoritative deadline before an
    # answer is rejected outright (network jitter tolerance)
    answer_grace_ms: int = 400
    # fallback question length when a question does not specify one
    default_time_limit: int = 20
    default_points: int = 1000

    # ---------------------------------------------------------------- cors
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"

    # -------------------------------------------------------- rate limiting
    #: Master switch - set false to disable every limit (useful in tests).
    rate_limit_enabled: bool = True
    #: Honour X-Forwarded-For / X-Real-IP. MUST be true behind the nginx
    #: reverse proxy, and false when uvicorn is exposed directly, otherwise a
    #: client can spoof its address and walk around every IP limit.
    rate_limit_trust_proxy: bool = True

    # -- auth (anonymous, keyed by IP) --
    auth_rate_window_seconds: int = 60
    auth_login_limit: int = 10
    auth_register_limit: int = 5
    auth_token_limit: int = 20  # phone verification + google oauth

    # -- AI generation (cost control; window is hourly) --
    ai_rate_window_seconds: int = 3600
    ai_generate_user_limit: int = 30
    ai_generate_ip_limit: int = 60
    ai_pdf_user_limit: int = 10
    ai_pdf_ip_limit: int = 20

    # ---------------------------------------------------------------- ai
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_timeout_seconds: float = 60.0
    #: total attempts (incl. the first) for transient provider failures
    groq_max_attempts: int = 3
    #: base seconds for exponential backoff between retries
    groq_retry_base_delay: float = 1.5
    ai_enabled: bool = True

    # ---------------------------------------------------------------- oauth (google)
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"

    # ---------------------------------------------------------------- firebase (phone auth)
    firebase_project_id: str | None = None
    firebase_private_key: str | None = None
    firebase_client_email: str | None = None

    # ------------------------------------------------------------ derived
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def sync_database_url(self) -> str:
        """Same database, but with a *synchronous* driver (used by Alembic)."""
        url = self.database_url
        if url.startswith("sqlite+aiosqlite"):
            return url.replace("sqlite+aiosqlite", "sqlite", 1)
        if url.startswith("postgresql+asyncpg"):
            return url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)
        return url

    # ------------------------------------------------------ safety rails
    @model_validator(mode="after")
    def _validate_production(self) -> "Settings":
        """Refuse to boot with development settings in production."""
        if not self.is_production:
            return self

        problems: list[str] = []

        secret = (self.secret_key or "").strip()
        if not secret or secret.lower() in _PLACEHOLDER_SECRETS or len(secret) < 32:
            problems.append(
                "SECRET_KEY must be a unique random string of at least 32 "
                "characters (generate with: python -c \"import secrets;"
                " print(secrets.token_urlsafe(48))\")"
            )

        if self.is_sqlite or not self.is_postgres:
            problems.append(
                "DATABASE_URL must be PostgreSQL in production, e.g. "
                "postgresql+asyncpg://user:pass@host:5432/dbname "
                f"(current scheme: {self.database_url.split(':', 1)[0] or 'unknown'})"
            )

        if self.debug:
            problems.append("DEBUG must be false in production")

        if self.auto_migrate:
            problems.append(
                "AUTO_MIGRATE must be false in production; run "
                "'alembic upgrade head' as an explicit deployment step"
            )

        origins = self.cors_origin_list
        if not origins:
            problems.append(
                "CORS_ORIGINS must list your production origin(s), e.g. "
                "https://playoot.example.com"
            )
        else:
            bad = [
                o
                for o in origins
                if o == "*" or any(m in o.lower() for m in _LOCAL_HOST_MARKERS)
            ]
            if bad:
                problems.append(
                    "CORS_ORIGINS must not contain '*' or localhost origins in "
                    f"production (found: {', '.join(bad)})"
                )

        if self.ai_enabled and not (self.groq_api_key or "").strip():
            problems.append("GROQ_API_KEY must be set when AI_ENABLED is true")

        if self.google_client_id:
            redirect = (self.google_redirect_uri or "").strip()
            if not redirect:
                problems.append(
                    "GOOGLE_REDIRECT_URI must be set when GOOGLE_CLIENT_ID is set"
                )
            elif not redirect.startswith("https://"):
                problems.append(
                    "GOOGLE_REDIRECT_URI must be an https:// URL in production"
                )
            elif any(m in redirect.lower() for m in _LOCAL_HOST_MARKERS):
                problems.append(
                    "GOOGLE_REDIRECT_URI must not point at localhost in production"
                )

        if problems:
            raise ProductionConfigError(
                "Invalid production configuration:\n  - " + "\n  - ".join(problems)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()