"""PLAYOOT IN EVERYWHERE API application factory.

Run with::

    uvicorn app.main:app --reload --port 8000     # from the backend/ folder
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.ai.base import QuizGenerationError
from app.api import api_router
from app.config import BACKEND_DIR, settings
from app.core.timeutil import iso, utcnow
from app.database import SessionLocal
from app.game.errors import GameError
from app.game.registry import get_registry
from app.ws.endpoint import router as ws_router

logger = logging.getLogger("playoot")


def _run_migrations() -> None:
    """Apply Alembic migrations using the synchronous driver.

    Alembic is the single source of truth for the schema; this only automates
    running it at startup during development (``AUTO_MIGRATE=false`` in
    production, where migrations are run out-of-band).
    """
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_migrate:
        try:
            await asyncio.to_thread(_run_migrations)
            logger.info("database schema is up to date")
        except Exception:
            logger.exception(
                "automatic migration failed - run 'alembic upgrade head' manually"
            )
    get_registry()
    logger.info(
        "%s %s ready (env=%s, ai=%s)",
        settings.app_name,
        __version__,
        settings.environment,
        "configured" if settings.groq_api_key else "not configured",
    )
    try:
        yield
    finally:
        await get_registry().shutdown()
        from app.database import dispose_engine

        await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} API",
        version=__version__,
        description=(
            "Server-authoritative multiplayer quiz engine. "
            "Gameplay happens over WebSockets at /ws/game/{pin}; everything "
            "else is REST under /api."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    app.include_router(ws_router)

    # ------------------------------------------------------- error handling
    @app.exception_handler(GameError)
    async def _game_error(_request: Request, exc: GameError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.to_payload()})

    @app.exception_handler(QuizGenerationError)
    async def _ai_error(_request: Request, exc: QuizGenerationError) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"detail": {"code": exc.code, "message": exc.message}}
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Normalise validation failures into the same error envelope."""
        errors = jsonable_encoder(exc.errors())
        first = errors[0] if errors else {}
        location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        message = first.get("msg", "The request was invalid.")
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "VALIDATION_ERROR",
                    "message": f"{location}: {message}" if location else message,
                    "details": {"errors": errors},
                }
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        """Last-resort handler.

        The traceback is logged server-side only; the client gets a stable,
        curated envelope. Without this, a framework-level leak (or DEBUG=true)
        could return stack traces, file paths or driver errors.
        """
        logger.exception("unhandled error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "code": "INTERNAL_ERROR",
                    "message": "Something went wrong on the server.",
                }
            },
        )

    # -------------------------------------------------------------- system
    @app.get("/", tags=["system"])
    async def root() -> dict:
        return {
            "name": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "rest": "/api",
            "websocket": "/ws/game/{gamePin}",
            "health": "/api/health",
            "readiness": "/api/ready",
        }

    @app.get("/api/health", tags=["system"])
    async def health() -> dict:
        """Liveness. Deliberately free of infrastructure detail so it is safe to
        expose publicly (no database DSN, no game PINs, no provider config)."""
        return {
            "status": "ok",
            "name": settings.app_name,
            "version": __version__,
            "environment": settings.environment,
            "serverTime": iso(utcnow()),
        }

    @app.get("/api/ready", tags=["system"])
    async def ready() -> JSONResponse:
        """Readiness: verifies the database is actually reachable.

        Still safe to expose - it reports the backend *type* only, never the
        DSN or credentials, and never lists live game PINs.
        """
        database_ok = True
        try:
            async with SessionLocal() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            logger.exception("readiness database probe failed")
            database_ok = False

        payload = {
            "ready": database_ok,
            "status": "ok" if database_ok else "degraded",
            "database": "postgresql" if settings.is_postgres else "sqlite",
            "databaseReachable": database_ok,
            "aiConfigured": bool(settings.groq_api_key) and settings.ai_enabled,
            "activeGames": len(get_registry().loaded_pins()),
            "serverTime": iso(utcnow()),
        }
        return JSONResponse(
            status_code=200 if database_ok else 503, content=payload
        )

    return app


app = create_app()