"""Quiz persistence helpers shared by the REST routes and the AI generator."""

from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz import Question, Quiz


def serialize_question(question: Question) -> dict[str, Any]:
    return {
        "id": question.id,
        "question_text": question.question_text,
        "question_type": question.question_type,
        "options": list(question.options or []),
        # authoring endpoint only - the authenticated owner may see this
        "correct_answer": question.correct_answer,
        "correct_answers": list(question.correct_answers or []),
        "explanation": question.explanation,
        "time_limit": question.time_limit,
        "points": question.points,
        "order_index": question.order_index,
    }


def serialize_quiz(quiz: Quiz, *, include_questions: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": quiz.id,
        "title": quiz.title,
        "description": quiz.description,
        "source_type": quiz.source_type,
        "created_at": quiz.created_at,
        "updated_at": quiz.updated_at,
        "question_count": len(quiz.questions or []),
        "winners_count": quiz.winners_count,
    }
    if include_questions:
        payload["questions"] = [
            serialize_question(q) for q in (quiz.questions or [])
        ]
    return payload


async def apply_questions(
    session: AsyncSession, quiz: Quiz, questions: Sequence[Any]
) -> None:
    """Replace a quiz's questions with the supplied list.

    ``questions`` may be ORM :class:`Question` objects, dicts shaped like
    :class:`app.schemas.api.QuestionIn`, or :class:`app.ai.base.GeneratedQuestion` dataclasses.
    """
    existing = (
        await session.scalars(select(Question).where(Question.quiz_id == quiz.id))
    ).all()
    for row in existing:
        await session.delete(row)
    await session.flush()

    for index, item in enumerate(questions):
        if hasattr(item, "model_dump"):
            data = item.model_dump()
        elif hasattr(item, "__dataclass_fields__"):
            # Handle GeneratedQuestion dataclass
            data = {f.name: getattr(item, f.name) for f in item.__dataclass_fields__.values()}
        else:
            data = dict(item)  # type: ignore[arg-type]
        options = [str(o).strip() for o in data.get("options", [])]
        qtype = data.get("question_type", "multiple_choice")
        session.add(
            Question(
                quiz_id=quiz.id,
                question_text=str(data["question_text"]).strip(),
                question_type=qtype,
                options=options,
                correct_answer=str(data.get("correct_answer") or "").strip(),
                correct_answers=data.get("correct_answers", []),
                explanation=data.get("explanation"),
                time_limit=int(data.get("time_limit") or 20),
                points=int(data.get("points") if data.get("points") is not None else 1000),
                order_index=index,
            )
        )
    await session.flush()