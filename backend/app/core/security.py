"""Password hashing and JWT issuing/verification.

Password hashing uses ``hashlib.pbkdf2_hmac`` (stdlib, no native build step)
with a per-user random salt.  Tokens are ordinary HS256 JWTs with a ``typ``
claim so a player token can never be replayed as a host token.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Any

import jwt

from app.config import settings
from app.core.timeutil import utcnow

_PBKDF2_ITERATIONS = 240_000
_PBKDF2_PREFIX = "pbkdf2_sha256"

TOKEN_TYPE_HOST = "access"
TOKEN_TYPE_PLAYER = "player"


# --------------------------------------------------------------- passwords
def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(raw: str) -> bytes:
    return base64.b64decode(raw.encode("ascii"))


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{_PBKDF2_PREFIX}${_PBKDF2_ITERATIONS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        prefix, iterations, salt_b64, digest_b64 = stored.split("$")
        if prefix != _PBKDF2_PREFIX:
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), _unb64(salt_b64), int(iterations)
        )
        return hmac.compare_digest(candidate, _unb64(digest_b64))
    except (ValueError, TypeError):
        return False


# ------------------------------------------------------------------- jwt
def _encode(payload: dict[str, Any], expires_minutes: int) -> str:
    now = utcnow()
    body = {
        **payload,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return jwt.encode(body, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int, email: str) -> str:
    """Host / dashboard token."""
    return _encode(
        {"sub": str(user_id), "email": email, "typ": TOKEN_TYPE_HOST},
        settings.access_token_expire_minutes,
    )


def create_player_token(player_id: int, game_id: int, game_pin: str) -> str:
    """Long-lived token that lets a player resume a game after a reconnect."""
    return _encode(
        {
            "sub": str(player_id),
            "gid": game_id,
            "pin": game_pin,
            "typ": TOKEN_TYPE_PLAYER,
        },
        60 * 24 * 2,
    )


def decode_token(token: str, *, expected_type: str | None = None) -> dict[str, Any] | None:
    """Decode + validate a token.  Returns ``None`` for anything invalid."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    if expected_type is not None and payload.get("typ") != expected_type:
        return None
    return payload