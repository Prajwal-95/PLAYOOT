"""Quiz CRUD + AI generation routes (REST).

The ``correct_answer`` field is returned here because these are the
authenticated authoring endpoints.  It is safe precisely because the gameplay
path never uses these schemas - during a live game the only thing a player can
see is what :mod:`app.game.serializer` decides to send.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import QuizGenerationError, get_quiz_generator
from app.ai.base import GenerationRequest
from app.ai.groq_generator import extract_text_from_pdf
from app.api.deps import get_current_user, limit_user_and_ip
from app.database import get_session
from app.models.quiz import Quiz
from app.models.user import User
from app.schemas.api import (
    GenerateQuizIn,
    GenerateQuizOut,
    GeneratedQuestionOut,
    QuizCreateIn,
    QuizOut,
    QuizSummaryOut,
    QuizUpdateIn,
)
from app.services.quiz_service import apply_questions, serialize_quiz

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


async def _owned_quiz(session: AsyncSession, quiz_id: int, user: User) -> Quiz:
    quiz = await session.get(Quiz, quiz_id)
    if quiz is None or quiz.creator_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "QUIZ_NOT_FOUND", "message": "Quiz not found."},
        )
    return quiz


@router.get("", response_model=list[QuizSummaryOut])
async def list_quizzes(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> list[dict]:
    quizzes = (
        await session.scalars(
            select(Quiz).where(Quiz.creator_id == user.id).order_by(Quiz.updated_at.desc())
        )
    ).all()
    return [serialize_quiz(q, include_questions=False) for q in quizzes]


@router.post("", response_model=QuizOut, status_code=status.HTTP_201_CREATED)
async def create_quiz(
    payload: QuizCreateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    quiz = Quiz(
        creator_id=user.id,
        title=payload.title.strip(),
        description=payload.description,
        source_type=payload.source_type,
        winners_count=payload.winners_count,
    )
    session.add(quiz)
    await session.flush()
    if payload.questions:
        await apply_questions(session, quiz, payload.questions)
    await session.commit()
    await session.refresh(quiz)
    return serialize_quiz(quiz)


@router.get("/{quiz_id}", response_model=QuizOut)
async def get_quiz(
    quiz_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    quiz = await _owned_quiz(session, quiz_id, user)
    return serialize_quiz(quiz)


@router.put("/{quiz_id}", response_model=QuizOut)
async def update_quiz(
    quiz_id: int,
    payload: QuizUpdateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    quiz = await _owned_quiz(session, quiz_id, user)
    if payload.title is not None:
        quiz.title = payload.title.strip()
    if payload.description is not None:
        quiz.description = payload.description
    if payload.winners_count is not None:
        quiz.winners_count = payload.winners_count
    if payload.questions is not None:
        await apply_questions(session, quiz, payload.questions)
    await session.commit()
    await session.refresh(quiz)
    return serialize_quiz(quiz)


@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_quiz(
    quiz_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    quiz = await _owned_quiz(session, quiz_id, user)
    await session.delete(quiz)
    await session.commit()
    return None


# ------------------------------------------------------------ ai generation
def _generation_request(payload: GenerateQuizIn) -> GenerationRequest:
    return GenerationRequest(
        source_type=payload.source_type,
        question_count=payload.question_count,
        question_types=payload.question_types,
        option_count=payload.option_count,
        difficulty=payload.difficulty,
        time_limit=payload.time_limit,
        points=payload.points,
        topic=payload.topic,
        prompt=payload.prompt,
        title=payload.title,
        extra={"custom_instructions": payload.custom_instructions} if payload.custom_instructions else {},
    )


def _to_generated_out(questions) -> list[GeneratedQuestionOut]:
    return [
        GeneratedQuestionOut(
            question_text=q.question_text,
            question_type=q.question_type,
            options=q.options,
            correct_answer=q.correct_answer,
            correct_answers=q.correct_answers,
            explanation=q.explanation,
            time_limit=q.time_limit,
            points=q.points,
        )
        for q in questions
    ]


async def _persist_generated(
    session: AsyncSession, user: User, title: str, source_type: str, questions,
    winners_count: int | None = None
) -> dict:
    quiz = Quiz(creator_id=user.id, title=title.strip(), source_type=source_type, winners_count=winners_count)
    session.add(quiz)
    await session.flush()
    await apply_questions(session, quiz, questions)
    await session.commit()
    await session.refresh(quiz)
    return serialize_quiz(quiz)


#: Client-safe copy per error code.
#:
#: The exception's own message is deliberately NOT forwarded: it is built from
#: upstream failure text and could carry provider URLs, response bodies or key
#: fragments. Only these curated strings ever reach a client.
_SAFE_GENERATION_MESSAGES: dict[str, str] = {
    "AI_NOT_CONFIGURED": "AI generation is not configured on this server.",
    "AI_DISABLED": "AI generation is disabled on this server.",
    "AI_PROVIDER_ERROR": "The AI provider could not be reached. Please try again.",
    "AI_NO_VALID_QUESTIONS": "The model did not return any usable questions. Try rephrasing the topic.",
    "AI_BAD_RESPONSE": "The AI provider returned an unusable response. Please try again.",
    "AI_GENERATION_FAILED": "The quiz could not be generated. Please try again.",
    "PDF_ENCRYPTED": "That PDF is password protected.",
    "PDF_UNREADABLE": "That file could not be read as a PDF.",
    "PDF_NO_TEXT": "No readable text was found in that PDF (is it a scan?).",
}

_GENERIC_GENERATION_MESSAGE = "The quiz could not be generated. Please try again."


def _generation_http_error(exc: QuizGenerationError) -> HTTPException:
    status_code = {
        "AI_NOT_CONFIGURED": status.HTTP_503_SERVICE_UNAVAILABLE,
        "AI_DISABLED": status.HTTP_503_SERVICE_UNAVAILABLE,
        "AI_PROVIDER_ERROR": status.HTTP_502_BAD_GATEWAY,
        "PDF_ENCRYPTED": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "PDF_UNREADABLE": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "PDF_NO_TEXT": status.HTTP_422_UNPROCESSABLE_ENTITY,
    }.get(exc.code, status.HTTP_422_UNPROCESSABLE_ENTITY)
    return HTTPException(
        status_code=status_code,
        detail={
            "code": exc.code,
            "message": _SAFE_GENERATION_MESSAGES.get(exc.code, _GENERIC_GENERATION_MESSAGE),
        },
    )


@router.post("/generate", response_model=GenerateQuizOut)
async def generate_quiz(
    payload: GenerateQuizIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(limit_user_and_ip("ai.generate.user", "ai.generate.ip")),
) -> dict:
    """Topic or prompt -> questions, via the configured ``QuizGenerator``."""
    try:
        generator = get_quiz_generator()
        questions = await generator.generate(_generation_request(payload))
    except QuizGenerationError as exc:
        raise _generation_http_error(exc) from exc

    title = payload.title or payload.topic or "Generated quiz"
    quiz = None
    if payload.save:
        quiz = await _persist_generated(
            session, user, title, payload.source_type, questions, payload.winners_count
        )
    return {
        "source_type": payload.source_type,
        "generated_count": len(questions),
        "questions": _to_generated_out(questions),
        "quiz": quiz,
        "winners_count": payload.winners_count,
    }


@router.post("/generate/pdf", response_model=GenerateQuizOut)
async def generate_quiz_from_pdf(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    question_count: int = Form(default=5),
    question_types: str = Form(default='["multiple_choice"]'),
    option_count: int = Form(default=4),
    difficulty: str = Form(default="mixed"),
    time_limit: int = Form(default=20),
    points: int = Form(default=1000),
    save: bool = Form(default=True),
    custom_instructions: str | None = Form(default=None),
    winners_count: Literal[1, 3, 5, 10] = Form(default=3),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(limit_user_and_ip("ai.pdf.user", "ai.pdf.ip")),
) -> dict:
    """PDF -> text -> questions.  The uploaded bytes never leave the server."""
    raw = await file.read()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "EMPTY_UPLOAD", "message": "The uploaded file was empty."},
        )
    try:
        text = extract_text_from_pdf(raw)
    except QuizGenerationError as exc:
        raise _generation_http_error(exc) from exc

    import json
    parsed_types = json.loads(question_types)
    
    request = GenerationRequest(
        source_type="pdf",
        question_count=max(1, min(int(question_count), 20)),
        question_types=parsed_types,
        option_count=max(2, min(int(option_count), 6)),
        difficulty=difficulty,
        time_limit=max(5, min(int(time_limit), 300)),
        points=max(0, int(points)),
        text=text,
        title=title or (file.filename or "PDF quiz"),
        extra={"custom_instructions": custom_instructions} if custom_instructions else {},
    )
    try:
        generator = get_quiz_generator()
        questions = await generator.generate(request)
    except QuizGenerationError as exc:
        raise _generation_http_error(exc) from exc

    quiz = None
    if save:
        quiz = await _persist_generated(
            session, user, request.title or "PDF quiz", "pdf", questions, winners_count
        )
    return {
        "source_type": "pdf",
        "generated_count": len(questions),
        "questions": _to_generated_out(questions),
        "quiz": quiz,
        "winners_count": winners_count,
    }