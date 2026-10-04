from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utcnow
from app.database import Base

if TYPE_CHECKING:  # pragma: no cover
    from app.models.quiz import Quiz

#: ``GameSession.mode``
MODE_INDIVIDUAL = "individual"
MODE_TEAM = "team"
GAME_MODES = (MODE_INDIVIDUAL, MODE_TEAM)

#: ``GameSession.status`` mirrors :class:`app.game.states.GameState` values.
STATUS_LOBBY = "LOBBY"
STATUS_QUESTION_ACTIVE = "QUESTION_ACTIVE"
STATUS_QUESTION_REVEAL = "QUESTION_REVEAL"
STATUS_LEADERBOARD = "LEADERBOARD"
STATUS_FINISHED = "FINISHED"
STATUS_CANCELLED = "CANCELLED"


class GameSession(Base):
    __tablename__ = "game_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    host_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Globally unique numeric PIN.  Generated server-side only.
    game_pin: Mapped[str] = mapped_column(String(12), nullable=False, unique=True, index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default=MODE_INDIVIDUAL)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=STATUS_LOBBY)

    #: index of the question currently on screen; -1 while in the lobby
    current_question_index: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    #: authoritative question window - the server owns the timer
    question_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    question_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    quiz: Mapped["Quiz"] = relationship(lazy="joined")
    players: Mapped[list["Player"]] = relationship(
        back_populates="game", cascade="all, delete-orphan", lazy="selectin"
    )
    teams: Mapped[list["Team"]] = relationship(
        back_populates="game", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GameSession id={self.id} pin={self.game_pin} status={self.status}>"
class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("game_id", "name", name="uq_teams_game_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    game: Mapped["GameSession"] = relationship(back_populates="teams")
    members: Mapped[list["Player"]] = relationship(back_populates="team")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Team id={self.id} name={self.name!r} score={self.score}>"


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("game_id", "nickname", name="uq_players_game_nickname"),
        Index("ix_players_game_team", "game_id", "team_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    nickname: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    connected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True
    )

    game: Mapped["GameSession"] = relationship(back_populates="players")
    team: Mapped["Team | None"] = relationship(back_populates="members")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Player id={self.id} nickname={self.nickname!r} score={self.score}>"


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (
        # hard guarantee: one answer per player per question per game
        UniqueConstraint("game_id", "question_id", "player_id", name="uq_answers_once"),
        Index("ix_answers_game_question", "game_id", "question_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    selected_answer: Mapped[int] = mapped_column(Integer, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    #: frozen at grading time so historical results never drift if the
    #: scoring formula is tuned later
    points_awarded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Answer player={self.player_id} q={self.question_id} "
            f"correct={self.is_correct} pts={self.points_awarded}>"
        )