"""Plain in-memory state containers used by the game engine.

These are deliberately dependency-free dataclasses so the engine can hold the
authoritative hot path entirely in memory while a copy is written through to
the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.core.timeutil import utcnow


@dataclass(frozen=True)
class QuizQuestion:
    """A question as the engine sees it - including the correct answer.

    Instances of this class are **never** serialised wholesale.  The serializer
    builds explicit payloads and simply leaves ``correct_answer`` out.
    """

    id: int
    order_index: int
    text: str
    options: list[str]
    correct_answer: str
    explanation: str | None = None
    time_limit: int = 20
    points: int = 1000

    @property
    def correct_index(self) -> int:
        try:
            return self.options.index(self.correct_answer)
        except ValueError:  # pragma: no cover - guarded at quiz save time
            return -1


@dataclass
class LivePlayer:
    id: int
    nickname: str
    score: int = 0
    connected: bool = True
    team_id: int | None = None
    user_id: int | None = None
    joined_at: datetime = field(default_factory=utcnow)


@dataclass
class LiveTeam:
    id: int
    name: str
    score: int = 0
    created_at: datetime = field(default_factory=utcnow)
    member_ids: list[int] = field(default_factory=list)

    @property
    def member_count(self) -> int:
        return len(self.member_ids)


@dataclass
class AnswerRecord:
    """Result of one graded submission, kept for the current question."""

    player_id: int
    question_id: int
    selected_answer: int
    is_correct: bool
    response_time_ms: int
    points_awarded: int
    submitted_at: datetime = field(default_factory=utcnow)