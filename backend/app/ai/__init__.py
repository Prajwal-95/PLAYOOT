"""Question generation, isolated from the game engine.

The engine only ever receives a ``Quiz`` and its ``Question`` rows.  It has no
knowledge of - and no dependency on - where those questions came from.  This
package is the only place that talks to an LLM provider, and the provider API
key never leaves the server.
"""

from app.ai.base import (
    GeneratedQuestion,
    GenerationRequest,
    QuizGenerationError,
    QuizGenerator,
)
from app.ai.factory import get_quiz_generator

__all__ = [
    "GeneratedQuestion",
    "GenerationRequest",
    "QuizGenerationError",
    "QuizGenerator",
    "get_quiz_generator",
]