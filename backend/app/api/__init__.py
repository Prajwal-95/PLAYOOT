"""REST router aggregation."""

from fastapi import APIRouter

from app.api import routes_auth, routes_game, routes_quiz

api_router = APIRouter()
api_router.include_router(routes_auth.router)
api_router.include_router(routes_quiz.router)
api_router.include_router(routes_game.router)

__all__ = ["api_router"]