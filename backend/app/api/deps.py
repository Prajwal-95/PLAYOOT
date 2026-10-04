"""Shared FastAPI dependencies for authentication."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.ratelimit import Decision, limiter
from app.core.security import TOKEN_TYPE_HOST, TOKEN_TYPE_PLAYER, decode_token
from app.database import get_session
from app.models.user import User


def _unauthorized(message: str, code: str = "UNAUTHORIZED") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Resolve the authenticated host from an ``Authorization: Bearer`` header."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("Sign in to continue.")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_token(token, expected_type=TOKEN_TYPE_HOST)
    if payload is None:
        raise _unauthorized("Your session has expired. Please sign in again.")
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise _unauthorized("Malformed session token.") from None
    user = await session.get(User, user_id)
    if user is None:
        raise _unauthorized("That account no longer exists.")
    return user


async def get_optional_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Like :func:`get_current_user`, but never fails.

    Players may optionally attach their host account when joining.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    payload = decode_token(authorization.split(" ", 1)[1].strip(), expected_type=TOKEN_TYPE_HOST)
    if payload is None:
        return None
    try:
        return await session.get(User, int(payload["sub"]))
    except (KeyError, TypeError, ValueError):
        return None


async def get_player_token(x_player_token: str | None = Header(default=None)) -> str:
    """Extract the player token issued by ``POST /api/games/{pin}/join``."""
    if not x_player_token or not x_player_token.strip():
        raise _unauthorized("Join the game again - your player session is missing.")
    payload = decode_token(x_player_token.strip(), expected_type=TOKEN_TYPE_PLAYER)
    if payload is None:
        raise _unauthorized("Your player session has expired. Please rejoin the game.")
    return x_player_token.strip()


# ============================================================ rate limiting

#: bucket -> (limit setting name, window setting name)
_BUCKET_SETTINGS: dict[str, tuple[str, str]] = {
    "auth.login": ("auth_login_limit", "auth_rate_window_seconds"),
    "auth.register": ("auth_register_limit", "auth_rate_window_seconds"),
    "auth.token": ("auth_token_limit", "auth_rate_window_seconds"),
    "ai.generate.user": ("ai_generate_user_limit", "ai_rate_window_seconds"),
    "ai.generate.ip": ("ai_generate_ip_limit", "ai_rate_window_seconds"),
    "ai.pdf.user": ("ai_pdf_user_limit", "ai_rate_window_seconds"),
    "ai.pdf.ip": ("ai_pdf_ip_limit", "ai_rate_window_seconds"),
}


def client_ip(request: Request) -> str:
    """Best-effort client address.

    Behind the bundled nginx proxy the real address only exists in a proxy
    header, so ``RATE_LIMIT_TRUST_PROXY=true`` is required there. Two details
    keep this safe:

    * ``X-Real-IP`` is preferred because the bundled nginx config *overwrites*
      it with ``$remote_addr``.
    * ``X-Forwarded-For`` may legally be a chain, so the **right-most** entry
      is used - the one our own proxy appended. Taking the left-most entry
      would trust whatever the client sent first.

    Set ``RATE_LIMIT_TRUST_PROXY=false`` whenever uvicorn is reachable
    directly, otherwise a client can spoof these headers and walk around every
    IP rate limit.
    """
    if settings.rate_limit_trust_proxy:
        real_ip = request.headers.get("x-real-ip")
        if real_ip and real_ip.strip():
            return real_ip.strip()
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            chain = [entry.strip() for entry in forwarded.split(",") if entry.strip()]
            if chain:
                return chain[-1]
    return request.client.host if request.client else "unknown"


def _resolve(bucket: str) -> tuple[int, int]:
    limit_attr, window_attr = _BUCKET_SETTINGS[bucket]
    return int(getattr(settings, limit_attr)), int(getattr(settings, window_attr))


def _too_many(decision: Decision) -> HTTPException:
    """A generic 429 that never leaks provider or internal details."""
    minutes = max(1, round(decision.retry_after / 60))
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": "RATE_LIMITED",
            "message": (
                "Too many requests. "
                f"Please try again in about {minutes} minute"
                f"{'s' if minutes != 1 else ''}."
            ),
        },
        headers={"Retry-After": str(decision.retry_after)},
    )


def limit_ip(bucket: str):
    """Rate-limit an anonymous endpoint by client IP.

    Usage::

        @router.post("/login")
        async def login(_rl: None = Depends(limit_ip("auth.login"))): ...
    """

    async def _dependency(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        limit, window = _resolve(bucket)
        decision = await limiter.hit(bucket, f"ip:{client_ip(request)}", limit, window)
        if not decision.allowed:
            raise _too_many(decision)

    return _dependency


def limit_user_and_ip(user_bucket: str, ip_bucket: str):
    """Rate-limit an authenticated endpoint by account *and* by IP.

    The account limit stops one host burning the shared AI budget; the IP limit
    stops many accounts behind a single address doing the same thing.
    """

    async def _dependency(request: Request, user: User = Depends(get_current_user)) -> None:
        if not settings.rate_limit_enabled:
            return

        user_limit, user_window = _resolve(user_bucket)
        decision = await limiter.hit(user_bucket, f"user:{user.id}", user_limit, user_window)
        if not decision.allowed:
            raise _too_many(decision)

        ip_limit, ip_window = _resolve(ip_bucket)
        decision = await limiter.hit(ip_bucket, f"ip:{client_ip(request)}", ip_limit, ip_window)
        if not decision.allowed:
            raise _too_many(decision)

    return _dependency