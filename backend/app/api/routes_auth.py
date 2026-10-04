"""Authentication routes (REST)."""

from __future__ import annotations

import logging

import httpx
import firebase_admin
from firebase_admin import auth as firebase_auth, credentials
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.api.deps import get_current_user, limit_ip
from app.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_session
from app.models.user import User
from app.schemas.api import TokenOut, UserLoginIn, UserOut, UserRegisterIn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# Initialize Firebase Admin SDK
_firebase_app = None
def get_firebase_app():
    global _firebase_app
    if _firebase_app is None:
        import json
        from pathlib import Path
        sa_path = Path(__file__).resolve().parents[3] / "firebase-service-account.json"
        # The JSON key is a long-lived credential. It is excluded from the image
        # by .dockerignore and must never be the production path: env vars are.
        if settings.is_production and sa_path.exists():
            logger.warning(
                "firebase-service-account.json present in production but will be "
                "ignored; set FIREBASE_* environment variables instead"
            )
        if sa_path.exists() and not settings.is_production:
            with open(sa_path) as f:
                sa_info = json.load(f)
            cred = credentials.Certificate(sa_info)
            _firebase_app = firebase_admin.initialize_app(cred)
        elif settings.firebase_project_id:
            # Environment variables (the supported production path)
            cred = credentials.Certificate({
                "type": "service_account",
                "project_id": settings.firebase_project_id,
                "private_key": settings.firebase_private_key.replace("\\n", "\n") if settings.firebase_private_key else "",
                "client_email": settings.firebase_client_email,
                "token_uri": "https://oauth2.googleapis.com/token",
            })
            _firebase_app = firebase_admin.initialize_app(cred)
    return _firebase_app


class PhoneVerifyRequest(BaseModel):
    phone_number: str
    firebase_token: str  # ID token from Firebase client after OTP verification


@router.post("/phone/verify", response_model=TokenOut)
async def phone_verify(
    payload: PhoneVerifyRequest,
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(limit_ip("auth.token")),
):
    """Verify Firebase phone OTP and create/login user."""
    get_firebase_app()
    
    if not settings.firebase_project_id:
        raise HTTPException(status_code=503, detail="Firebase not configured")
    
    try:
        # Verify the Firebase ID token
        decoded_token = firebase_auth.verify_id_token(payload.firebase_token)
        
        # Extract phone number from token
        phone_number = decoded_token.get("phone_number")
        if not phone_number:
            raise HTTPException(status_code=400, detail="Phone number not in token")
        
        if phone_number != payload.phone_number:
            raise HTTPException(status_code=400, detail="Phone number mismatch")
        
        firebase_uid = decoded_token["uid"]
        
        # Find or create user
        user = await session.scalar(
            select(User).where(User.provider_id == firebase_uid, User.auth_provider == "phone")
        )
        
        if not user:
            user = User(
                name=f"User {phone_number[-4:]}",
                email=f"phone_{firebase_uid}@playoot.local",  # placeholder email
                auth_provider="phone",
                provider_id=firebase_uid,
            )
            session.add(user)
        
        await session.commit()
        await session.refresh(user)
        
        return TokenOut(
            access_token=create_access_token(user.id, user.email),
            user=UserOut.model_validate(user),
        )
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(status_code=400, detail="Invalid Firebase token")
    except HTTPException:
        raise
    except Exception:
        # Never echo the underlying error: Firebase/transport exceptions can
        # carry project identifiers, endpoints and internal detail.
        logger.exception("phone verification failed")
        raise HTTPException(
            status_code=400, detail="Phone verification failed. Please try again."
        ) from None


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserRegisterIn,
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(limit_ip("auth.register")),
) -> TokenOut:
    existing = await session.scalar(
        select(User.id).where(func.lower(User.email) == payload.email)
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "EMAIL_TAKEN", "message": "That email is already registered."},
        )
    try:
        password_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_PASSWORD", "message": str(exc)},
        ) from exc

    user = User(name=payload.name, email=payload.email, password_hash=password_hash, auth_provider="email")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return TokenOut(
        access_token=create_access_token(user.id, user.email),
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=TokenOut)
async def login(
    payload: UserLoginIn,
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(limit_ip("auth.login")),
) -> TokenOut:
    user = await session.scalar(
        select(User).where(func.lower(User.email) == payload.email)
    )
    if user is None or user.auth_provider != "email" or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Incorrect email or password."},
        )
    return TokenOut(
        access_token=create_access_token(user.id, user.email),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


# ===================== GOOGLE OAUTH =====================

@router.get("/google")
async def google_login(_rl: None = Depends(limit_ip("auth.token"))):
    """Redirect to Google OAuth consent screen."""
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    
    scope = "openid email profile"
    redirect_uri = settings.google_redirect_uri
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.google_client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope}"
        "&access_type=offline"
        "&prompt=consent"
    )
    return RedirectResponse(url=auth_url)


@router.get("/google/callback")
async def google_callback(
    code: str,
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(limit_ip("auth.token")),
):
    """Handle Google OAuth callback."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    # Exchange code for tokens
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }
    
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(token_url, data=data)
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange code for token")
        tokens = token_resp.json()

    # Verify ID token and get user info
    try:
        idinfo = id_token.verify_oauth2_token(
            tokens["id_token"],
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID token")

    google_sub = idinfo["sub"]
    email = idinfo["email"]
    name = idinfo.get("name", email.split("@")[0])
    picture = idinfo.get("picture")

    # Find or create user
    user = await session.scalar(
        select(User).where(User.provider_id == google_sub, User.auth_provider == "google")
    )
    
    if not user:
        # Check if email exists with email provider
        user = await session.scalar(
            select(User).where(func.lower(User.email) == email)
        )
        if user:
            # Link Google account to existing email account
            user.auth_provider = "google"
            user.provider_id = google_sub
            user.avatar_url = picture
        else:
            # Create new Google user
            user = User(
                name=name,
                email=email,
                auth_provider="google",
                provider_id=google_sub,
                avatar_url=picture,
            )
            session.add(user)
    
    await session.commit()
    await session.refresh(user)

    # Redirect to frontend with token in URL fragment
    frontend_url = settings.cors_origin_list[0] if settings.cors_origin_list else "http://localhost:5175"
    token = create_access_token(user.id, user.email)
    redirect_url = f"{frontend_url}/auth/callback#access_token={token}&token_type=bearer&user_id={user.id}"
    return RedirectResponse(url=redirect_url)