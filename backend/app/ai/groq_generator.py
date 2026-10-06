"""Groq-backed question generator.

This is the *only* module that touches the Groq SDK, and the API key is read
from server-side settings only - it is never accepted from a client and never
returned in a response or log line.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace

from app.ai.base import (
    GeneratedQuestion,
    GenerationRequest,
    MAX_QUESTIONS_PER_CALL,
    QuizGenerationError,
    QuizGenerator,
    build_system_prompt,
    build_user_prompt,
    extract_json,
    normalise_questions,
)

logger = logging.getLogger(__name__)

#: Provider exceptions that are worth retrying: rate limits, timeouts,
#: dropped connections and 5xx. Auth / not-found failures are NOT retried -
#: they will never succeed and should surface immediately.
_RETRYABLE_ERRORS = frozenset(
    {
        "RateLimitError",
        "APITimeoutError",
        "APIConnectionError",
        "InternalServerError",
    }
)


class GroqQuizGenerator(QuizGenerator):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        max_attempts: int = 3,
        retry_base_delay: float = 1.5,
    ) -> None:
        if not api_key:
            raise QuizGenerationError(
                "Groq is not configured on the server (missing GROQ_API_KEY).",
                code="AI_NOT_CONFIGURED",
            )
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._max_attempts = max(1, int(max_attempts))
        self._retry_base_delay = max(0.0, float(retry_base_delay))

    @property
    def provider(self) -> str:
        return "groq"

    async def _create_completion(self, client, messages, *, use_json_mode: bool):
        """Call Groq, retrying only transient failures with exponential backoff."""
        last_exc: Exception | None = None

        for attempt in range(self._max_attempts):
            kwargs = {
                "model": self._model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 4000,
            }
            if use_json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            try:
                return await client.chat.completions.create(**kwargs)
            except Exception as exc:  # noqa: BLE001 - mapped below
                last_exc = exc
                name = type(exc).__name__
                if name not in _RETRYABLE_ERRORS or attempt == self._max_attempts - 1:
                    raise
                delay = self._retry_base_delay * (2**attempt)
                logger.warning(
                    "transient Groq error %s; retrying in %.1fs (attempt %d/%d)",
                    name,
                    delay,
                    attempt + 1,
                    self._max_attempts,
                )
                await asyncio.sleep(delay)

        raise last_exc if last_exc else RuntimeError("unreachable")

    async def _complete(self, client, messages: list[dict]) -> str:
        """One model call -> raw assistant content, with the json-mode fallback."""
        try:
            completion = await self._create_completion(
                client, messages, use_json_mode=True
            )
        except Exception as exc:
            # Only a 400 means "this model rejected response_format". Every
            # other failure (auth, not-found, transient-after-retries) must
            # surface immediately - retrying it just burns another call.
            if type(exc).__name__ != "BadRequestError":
                raise
            # Some models reject response_format - retry once in plain mode.
            logger.info(
                "Groq json_object mode unavailable (%s), retrying without it",
                type(exc).__name__,
            )
            completion = await self._create_completion(
                client, messages, use_json_mode=False
            )
        return (completion.choices[0].message.content or "") if completion.choices else ""

    async def generate(self, request: GenerationRequest) -> list[GeneratedQuestion]:
        # imported lazily so a missing optional dependency cannot break startup
        try:
            from groq import AsyncGroq
        except ImportError as exc:  # pragma: no cover
            raise QuizGenerationError(
                "The 'groq' package is not installed on the server.",
                code="AI_NOT_CONFIGURED",
            ) from exc

        target = max(1, int(request.question_count))
        client = AsyncGroq(api_key=self._api_key, timeout=self._timeout)

        collected: list[GeneratedQuestion] = []
        seen: set[str] = set()

        # Request in rounds of at most MAX_QUESTIONS_PER_CALL so one big answer
        # never has to fit inside a single response (which would be truncated at
        # max_tokens and silently return fewer questions than were asked for).
        # The extra two rounds let us recover from a short or unusable batch.
        rounds_needed = (target + MAX_QUESTIONS_PER_CALL - 1) // MAX_QUESTIONS_PER_CALL
        max_rounds = rounds_needed + 2

        try:
            for _ in range(max_rounds):
                if len(collected) >= target:
                    break

                remaining = target - len(collected)
                chunk = replace(
                    request, question_count=min(remaining, MAX_QUESTIONS_PER_CALL)
                )
                messages = [
                    {"role": "system", "content": build_system_prompt(chunk)},
                    {"role": "user", "content": build_user_prompt(chunk)},
                ]
                if collected:
                    # Tell the model what it already produced so later rounds
                    # add NEW questions instead of repeats (repeats would be
                    # dropped, leaving us short of the requested count).
                    messages.append(
                        {
                            "role": "user",
                            "content": "Already covered - write DIFFERENT questions:\n- "
                            + "\n- ".join(
                                q.question_text for q in collected[-40:]
                            ),
                        }
                    )

                content = await self._complete(client, messages)

                try:
                    batch = normalise_questions(extract_json(content), chunk)
                except QuizGenerationError as exc:
                    if not collected:
                        raise
                    # First round failed as-is: report it unchanged. A later
                    # round failing is recoverable - keep asking for the
                    # remainder rather than throwing away what we already have.
                    logger.warning(
                        "groq round discarded (%s): %s", exc.code, exc.message
                    )
                    continue

                for question in batch:
                    key = question.question_text.strip().lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    collected.append(question)
                    if len(collected) >= target:
                        break
        except QuizGenerationError:
            raise
        except Exception as exc:
            logger.warning("Groq generation failed: %s", type(exc).__name__)
            raise QuizGenerationError(
                "The AI provider could not be reached. Please try again.",
                code="AI_PROVIDER_ERROR",
            ) from exc

        if len(collected) < target:
            # Never silently return a shorter quiz than was asked for.
            raise QuizGenerationError(
                f"The AI returned {len(collected)} of the {target} questions "
                "requested. Please try again.",
                code="AI_INCOMPLETE",
            )

        logger.info(
            "groq generated %d/%d questions (model=%s, rounds=%d)",
            len(collected),
            target,
            self._model,
            rounds_needed,
        )
        return collected


def extract_text_from_pdf(data: bytes, *, max_chars: int = 40_000) -> str:
    """Pull plain text out of an uploaded PDF using ``pypdf``."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise QuizGenerationError(
            "PDF support requires the 'pypdf' package on the server.",
            code="AI_NOT_CONFIGURED",
        ) from exc

    import io

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise QuizGenerationError(
                    "That PDF is password protected.", code="PDF_ENCRYPTED"
                ) from exc
        chunks = [(page.extract_text() or "") for page in reader.pages]
    except QuizGenerationError:
        raise
    except Exception as exc:
        raise QuizGenerationError(
            "That file could not be read as a PDF.", code="PDF_UNREADABLE"
        ) from exc

    text = "\n".join(chunks).strip()
    if len(text) < 40:
        raise QuizGenerationError(
            "No readable text was found in that PDF (is it a scan?).",
            code="PDF_NO_TEXT",
        )
    return text[:max_chars]