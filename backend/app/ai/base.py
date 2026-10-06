"""Provider-agnostic generation contract, prompt building and validation.

Anything shared by every provider (prompt engineering, JSON repair, strict
validation of the returned questions) lives here so adding a second provider is
a small class rather than a second copy of the rules.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

#: Hard ceiling on how many questions a single generation request may ask
#: for.  Enforced by ``GenerateQuizIn.question_count`` (``le=``) and by the
#: PDF generation route's clamp, and mirrored on the frontend as
#: ``MAX_GENERATED_QUESTIONS`` so the UI can never offer a value the API
#: rejects.
MAX_QUESTIONS_PER_QUIZ = 50

#: The model is called in rounds of at most this many questions so a big
#: request (up to ``MAX_QUESTIONS_PER_QUIZ``) never depends on one huge
#: response that could hit ``max_tokens`` and come back truncated - which is
#: how a request for 50 could otherwise silently come back as 10 or 20.
MAX_QUESTIONS_PER_CALL = 10


class QuizGenerationError(Exception):
    """Raised when generation cannot produce usable questions.

    Carries a machine-readable ``code`` so the REST layer can turn it into a
    meaningful, non-silent failure.
    """

    def __init__(self, message: str, *, code: str = "AI_GENERATION_FAILED") -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class GeneratedQuestion:
    question_text: str
    question_type: str = "multiple_choice"  # multiple_choice, multiple_answer, fill_blank, true_false
    options: list[str] = field(default_factory=list)
    correct_answer: str = ""
    correct_answers: list[str] = field(default_factory=list)
    explanation: str | None = None
    time_limit: int = 20
    points: int = 1000


@dataclass
class GenerationRequest:
    """Everything a generator may need, already validated by the API schema."""

    source_type: str  # "topic" | "prompt" | "pdf"
    question_count: int = 5
    question_types: list[str] = field(default_factory=lambda: ["multiple_choice"])
    option_count: int = 4
    difficulty: str = "mixed"
    time_limit: int = 20
    points: int = 1000
    topic: str | None = None
    prompt: str | None = None
    text: str | None = None
    title: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def instruction(self) -> str:
        """The user-facing part of the prompt, per source type."""
        if self.source_type == "topic":
            return f"Create a quiz about the topic: {self.topic}."
        if self.source_type == "pdf":
            return "Create a quiz covering the key facts in the document below."
        return self.prompt or self.topic or ""


#: Hard ceiling on document text handed to the model.
MAX_SOURCE_CHARS = 24_000


def build_system_prompt(request: GenerationRequest) -> str:
    types_str = ", ".join(request.question_types)
    return (
        "You are a quiz author for a live multiplayer trivia game.\n"
        "Return ONLY a JSON object - no prose, no markdown - matching exactly:\n"
        '{"questions":[{"question_text":"...","question_type":"multiple_choice|multiple_answer|fill_blank|true_false","options":["...","..."],"correct_answer":"...","correct_answers":["..."],"explanation":"..."}]}\n'
        "Hard rules:\n"
        f"1. Produce exactly {request.question_count} questions.\n"
        f"2. Use ONLY these question types: {types_str}.\n"
        f"3. For multiple_choice/multiple_answer: each question must have exactly {request.option_count} options.\n"
        "4. For true_false: options MUST be [\"True\", \"False\"] only.\n"
        "5. For fill_blank: options MUST be empty array [], correct_answer is the expected text.\n"
        "6. For multiple_answer: correct_answers MUST be a list of 2+ option texts from the options array.\n"
        "7. For multiple_choice: correct_answer MUST be copied EXACTLY from one option.\n"
        "8. 'explanation' is one short sentence justifying the answer.\n"
        "9. Options must be short (max ~60 chars), mutually exclusive, no repeats within a question.\n"
        "10. Questions must be unambiguous, factually correct and self-contained.\n"
        "11. Output valid JSON only."
    )


def build_user_prompt(request: GenerationRequest) -> str:
    parts = [request.instruction()]
    parts.append(
        f"Difficulty: {request.difficulty}. "
        f"Number of questions: {request.question_count}. "
        f"Options per question: {request.option_count}."
    )
    if request.title:
        parts.append(f"Quiz title hint: {request.title}.")
    if request.source_type == "pdf" and request.text:
        parts.append("DOCUMENT:\n" + request.text[:MAX_SOURCE_CHARS])
    # Add custom instructions if provided
    custom = request.extra.get("custom_instructions") if request.extra else None
    if custom:
        parts.append("ADDITIONAL INSTRUCTIONS:\n" + custom.strip())
    return "\n\n".join(p for p in parts if p)


#: Matches a ```json ... ``` (or bare ``` ... ```) fenced block.
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(raw: str) -> dict[str, Any]:
    """Best-effort pull of a JSON object out of a model response."""
    if not raw or not raw.strip():
        raise QuizGenerationError("The model returned an empty response.")
    text = raw.strip()
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise QuizGenerationError(
                "The model did not return valid JSON.", code="AI_BAD_RESPONSE"
            ) from None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise QuizGenerationError(
                f"The model returned malformed JSON: {exc.msg}", code="AI_BAD_RESPONSE"
            ) from exc
    if isinstance(parsed, list):
        return {"questions": parsed}
    if not isinstance(parsed, dict):
        raise QuizGenerationError(
            "The model returned an unexpected JSON shape.", code="AI_BAD_RESPONSE"
        )
    return parsed


def normalise_questions(
    payload: dict[str, Any], request: GenerationRequest
) -> list[GeneratedQuestion]:
    """Validate model output into engine-ready questions.

    Anything that does not satisfy the rules is dropped rather than silently
    repaired, and a generation that yields nothing usable raises.
    """
    raw_items = payload.get("questions") or payload.get("items") or []
    if not isinstance(raw_items, list):
        raise QuizGenerationError(
            "The model response did not contain a question list.", code="AI_BAD_RESPONSE"
        )

    questions: list[GeneratedQuestion] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("question_text") or item.get("question") or "").strip()
        qtype = str(item.get("question_type") or "multiple_choice").strip().lower()
        if qtype not in ("multiple_choice", "multiple_answer", "fill_blank", "true_false"):
            continue
        options = item.get("options") or []
        correct = str(item.get("correct_answer") or item.get("answer") or "").strip()
        correct_multi = item.get("correct_answers") or []
        if not isinstance(correct_multi, list):
            correct_multi = []
        if not text:
            continue

        # Validate per question type
        if qtype == "fill_blank":
            if not correct:
                continue
            options = []
        elif qtype == "true_false":
            if set(options) != {"True", "False"}:
                continue
            if correct not in ("True", "False"):
                continue
        elif qtype == "multiple_answer":
            if len(options) < 2:
                continue
            if len(correct_multi) < 2:
                continue
            # ensure all correct_answers are in options
            if not all(ans in options for ans in correct_multi):
                continue
        else:  # multiple_choice
            if len(options) < 2:
                continue
            if correct not in options:
                # tolerate case/whitespace
                match = next((o for o in options if o.lower() == correct.lower()), None)
                if match is None:
                    continue
                correct = match

        cleaned: list[str] = []
        for option in options:
            value = str(option).strip()
            if value and value not in cleaned:
                cleaned.append(value)
        # honour the requested option count when the model over-produces (except true_false/fill_blank)
        if qtype not in ("true_false", "fill_blank"):
            cleaned = cleaned[: request.option_count]

        # Re-validate correct answers against cleaned options
        if qtype in ("multiple_choice", "true_false"):
            if correct not in cleaned:
                match = next((o for o in cleaned if o.lower() == correct.lower()), None)
                if match is None:
                    continue
                correct = match
        elif qtype == "multiple_answer":
            correct_multi = [ans for ans in correct_multi if ans in cleaned]
            if len(correct_multi) < 2:
                continue

        explanation = item.get("explanation")
        questions.append(
            GeneratedQuestion(
                question_text=text,
                question_type=qtype,
                options=cleaned,
                correct_answer=correct,
                correct_answers=correct_multi,
                explanation=str(explanation).strip() if explanation else None,
                time_limit=request.time_limit,
                points=request.points,
            )
        )
        if len(questions) >= request.question_count:
            break

    if not questions:
        raise QuizGenerationError(
            "The model did not return any usable questions. Try rephrasing the topic.",
            code="AI_NO_VALID_QUESTIONS",
        )
    return questions


class QuizGenerator(ABC):
    """Contract every question provider implements."""

    @property
    @abstractmethod
    def provider(self) -> str:
        """Short provider identifier, e.g. ``groq``."""

    @abstractmethod
    async def generate(self, request: GenerationRequest) -> list[GeneratedQuestion]:
        """Return 1..``request.question_count`` validated questions."""

    async def close(self) -> None:  # pragma: no cover - optional cleanup
        return None