"""Chooses the active :class:`~app.ai.base.QuizGenerator`.

Swapping providers (or returning a fake generator in tests) is a change to this
function only - the routes and the engine never import a concrete provider.
"""

from __future__ import annotations

from app.ai.base import QuizGenerator
from app.config import settings
from app.ai.groq_generator import GroqQuizGenerator


def get_quiz_generator() -> QuizGenerator:
    """Return the configured generator, or raise a clear configuration error."""
    from app.ai.base import QuizGenerationError

    if not settings.ai_enabled:
        raise QuizGenerationError(
            "AI generation is disabled on this server.", code="AI_DISABLED"
        )
    if not settings.groq_api_key:
        raise QuizGenerationError(
            "AI generation is not configured: set GROQ_API_KEY on the server.",
            code="AI_NOT_CONFIGURED",
        )
    return GroqQuizGenerator(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        timeout=settings.groq_timeout_seconds,
        max_attempts=settings.groq_max_attempts,
        retry_base_delay=settings.groq_retry_base_delay,
    )