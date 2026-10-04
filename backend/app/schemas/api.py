"""REST request/response schemas.

Pydantic models are only used at the HTTP boundary.  Nothing here is used by
the WebSocket gameplay path, which has its own explicit payload builders in
:mod:`app.game.serializer`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import settings

SourceType = Literal["topic", "pdf", "prompt", "manual"]
GameMode = Literal["individual", "team"]

_EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


# ------------------------------------------------------------------- auth
class UserRegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=255, pattern=_EMAIL_RE)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Name cannot be blank.")
        return cleaned


class UserLoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.strip().lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    auth_provider: str
    provider_id: str | None = None
    avatar_url: str | None = None
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ------------------------------------------------------------------- quiz
class QuestionIn(BaseModel):
    question_text: str = Field(min_length=3, max_length=2000)
    question_type: Literal["multiple_choice", "multiple_answer", "fill_blank", "true_false"] = "multiple_choice"
    options: list[str] = Field(default_factory=list, max_length=6)
    correct_answer: str = Field(default="", max_length=300)
    correct_answers: list[str] = Field(default_factory=list)
    explanation: str | None = Field(default=None, max_length=2000)
    time_limit: int = Field(default=20, ge=5, le=300)
    points: int = Field(default=1000, ge=0, le=100_000)

    @field_validator("options")
    @classmethod
    def _clean_options(cls, value: list[str]) -> list[str]:
        cleaned = [o.strip() for o in value]
        if any(not o for o in cleaned):
            raise ValueError("Answer options cannot be blank.")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Answer options must be unique.")
        return cleaned

    @model_validator(mode="after")
    def _validate_for_type(self) -> "QuestionIn":
        qt = self.question_type
        if qt == "fill_blank":
            if self.options:
                raise ValueError("fill_blank questions must not have options.")
            if not self.correct_answer:
                raise ValueError("fill_blank questions require correct_answer.")
        elif qt == "true_false":
            if set(self.options) != {"True", "False"}:
                raise ValueError("true_false questions must have options ['True', 'False'].")
            if self.correct_answer not in ("True", "False"):
                raise ValueError("true_false correct_answer must be 'True' or 'False'.")
        elif qt == "multiple_answer":
            if len(self.options) < 2:
                raise ValueError("multiple_answer needs at least 2 options.")
            if len(self.correct_answers) < 2:
                raise ValueError("multiple_answer needs at least 2 correct_answers.")
            for ans in self.correct_answers:
                if ans not in self.options:
                    raise ValueError(f"correct_answers item {ans!r} must be in options.")
        else:  # multiple_choice
            if len(self.options) < 2:
                raise ValueError("multiple_choice needs at least 2 options.")
            if self.correct_answer not in self.options:
                raise ValueError(f"correct_answer {self.correct_answer!r} must match one option exactly.")
        return self


class QuizCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    source_type: SourceType = "manual"
    questions: list[QuestionIn] = Field(default_factory=list)


class QuizUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    questions: list[QuestionIn] | None = None


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_text: str
    question_type: str = "multiple_choice"
    options: list[str] = []
    correct_answer: str = ""
    correct_answers: list[str] = []
    explanation: str | None = None
    time_limit: int
    points: int
    order_index: int


class QuizSummaryOut(BaseModel):
    id: int
    title: str
    description: str | None
    source_type: str
    created_at: datetime
    updated_at: datetime
    question_count: int


class QuizOut(QuizSummaryOut):
    questions: list[QuestionOut]
    winners_count: Literal[1, 3, 5, 10] | None = None
# ------------------------------------------------------------- ai generation
class GenerateQuizIn(BaseModel):
    source_type: Literal["topic", "prompt"] = "topic"
    topic: str | None = Field(default=None, max_length=300)
    prompt: str | None = Field(default=None, max_length=2000)
    title: str | None = Field(default=None, max_length=160)
    question_count: int = Field(default=5, ge=1, le=20)
    question_types: list[Literal["multiple_choice", "multiple_answer", "fill_blank", "true_false"]] = Field(
        default_factory=lambda: ["multiple_choice"]
    )
    option_count: int = Field(default=4, ge=2, le=6)
    difficulty: Literal["easy", "medium", "hard", "mixed"] = "mixed"
    time_limit: int = Field(default=20, ge=5, le=300)
    points: int = Field(default=1000, ge=0, le=100_000)
    save: bool = True
    custom_instructions: str | None = Field(default=None, max_length=5000)
    winners_count: Literal[1, 3, 5, 10] = Field(default=3, description="Number of winners to announce")

    @model_validator(mode="after")
    def _require_instruction(self) -> "GenerateQuizIn":
        if self.source_type == "topic" and not (self.topic or "").strip():
            raise ValueError("'topic' is required when source_type is 'topic'.")
        if self.source_type == "prompt" and not (self.prompt or "").strip():
            raise ValueError("'prompt' is required when source_type is 'prompt'.")
        return self


class GeneratedQuestionOut(BaseModel):
    question_text: str
    question_type: Literal["multiple_choice", "multiple_answer", "fill_blank", "true_false"] = "multiple_choice"
    options: list[str] = []
    correct_answer: str = ""
    correct_answers: list[str] = []
    explanation: str | None = None
    time_limit: int
    points: int


class GenerateQuizOut(BaseModel):
    source_type: str
    generated_count: int
    questions: list[GeneratedQuestionOut]
    quiz: QuizOut | None = None
    winners_count: Literal[1, 3, 5, 10] | None = None


# ------------------------------------------------------------------- game
class GameCreateIn(BaseModel):
    quiz_id: int = Field(gt=0)
    mode: GameMode = "individual"


class GameLookupOut(BaseModel):
    game_id: int
    game_pin: str
    mode: str
    status: str
    quiz_id: int
    quiz_title: str
    question_count: int
    player_count: int
    team_count: int
    max_team_size: int
    joinable: bool
    created_at: datetime


class JoinGameIn(BaseModel):
    nickname: str = Field(
        min_length=settings.nickname_min_length, max_length=settings.nickname_max_length
    )
    team_id: int | None = None

    @field_validator("nickname")
    @classmethod
    def _clean(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Nickname cannot be blank.")
        if not all(ch.isalnum() or ch in " ._-'" for ch in cleaned):
            raise ValueError("Nickname may only contain letters, numbers and . _ - '")
        return cleaned


class PlayerOut(BaseModel):
    player_id: int
    nickname: str
    score: int
    connected: bool
    team_id: int | None
    team_name: str | None = None


class JoinGameOut(BaseModel):
    player: PlayerOut
    #: signed token that lets this player resume after a reconnect
    player_token: str
    game: GameLookupOut


class TeamCreateIn(BaseModel):
    name: str = Field(
        min_length=settings.team_name_min_length, max_length=settings.team_name_max_length
    )
    player_id: int | None = None
    join: bool = True

    @field_validator("name")
    @classmethod
    def _clean(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Team name cannot be blank.")
        return cleaned


class TeamJoinIn(BaseModel):
    team_id: int = Field(gt=0)
    player_id: int | None = None


class TeamOut(BaseModel):
    team_id: int
    name: str
    score: int
    member_count: int
    max_size: int
    is_full: bool
    members: list[PlayerOut]


class LobbyOut(BaseModel):
    game: GameLookupOut
    players: list[PlayerOut]
    teams: list[TeamOut]