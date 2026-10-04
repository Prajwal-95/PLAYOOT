from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utcnow
from app.database import Base

if TYPE_CHECKING:  # pragma: no cover
    from app.models.user import User

#: ``Quiz.source_type`` - how the questions got into the quiz.
SOURCE_TYPES = ("topic", "pdf", "prompt", "manual")

#: Question types supported
QUESTION_TYPES = (
    "multiple_choice",   # single correct answer (traditional)
    "multiple_answer",   # multiple correct answers
    "fill_blank",        # fill in the blank (no options, free text)
    "true_false",        # True/False
)


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    winners_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=3)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    creator: Mapped["User"] = relationship(back_populates="quizzes", lazy="joined")
    questions: Mapped[list["Question"]] = relationship(
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="Question.order_index",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Quiz id={self.id} title={self.title!r}>"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    #: question type: multiple_choice, multiple_answer, fill_blank, true_false
    question_type: Mapped[str] = mapped_column(String(20), nullable=False, default="multiple_choice")
    #: list[str] of answer options. For fill_blank this is empty.
    options: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    #: canonical text of the correct option (for single-answer types).
    correct_answer: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    #: for multiple_answer type: list of correct option texts
    correct_answers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    quiz: Mapped["Quiz"] = relationship(back_populates="questions")

    @property
    def correct_index(self) -> int:
        """Index of ``correct_answer`` inside ``options`` (-1 if inconsistent)."""
        options: list[Any] = list(self.options or [])
        try:
            return options.index(self.correct_answer)
        except ValueError:  # pragma: no cover - guarded by validation
            return -1

    @property
    def correct_indices(self) -> list[int]:
        """Indices of ``correct_answers`` inside ``options``."""
        options: list[Any] = list(self.options or [])
        return [i for i, opt in enumerate(options) if opt in (self.correct_answers or [])]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Question id={self.id} quiz_id={self.quiz_id} type={self.question_type} idx={self.order_index}>"