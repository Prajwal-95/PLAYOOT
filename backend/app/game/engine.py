"""The authoritative game engine.

One :class:`GameEngine` instance owns the live state of one game.  It is the
only place in the system that may:

* decide which question is on screen,
* decide when a question starts and ends (the server owns the timer),
* decide whether an answer is correct,
* decide how many points an answer is worth,
* change the game state,
* broadcast gameplay events.

Everything a client sends is an *intent* that the engine validates and either
accepts or rejects with a typed :class:`GameError`.

Concurrency model
-----------------
Every mutation runs inside ``self.lock``.  That makes "two players answer at
exactly the same millisecond" and "the timer fires while a player answers"
safe: the duplicate-answer check, the deadline check and the state transition
are all inside one critical section, so they cannot interleave.

Durability model
----------------
Live state lives in memory for speed, but every meaningful change is written
through to the database in a short-lived session.  A process restart therefore
loses nothing important: :meth:`GameEngine.load` rebuilds the engine - including
which players already answered - straight from the ``answers`` table.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.core.timeutil import as_utc, iso, ms_between, utcnow
from app.game.errors import GameError, GameErrorCode
from app.game.events import WSEventType
from app.game.live import AnswerRecord, LivePlayer, LiveTeam, QuizQuestion
from app.game.manager import ConnectionManager, manager as default_manager
from app.game.scoring import ScoringStrategy, scoring_service, team_scoring_service
from app.game.serializer import (
    leaderboard_payload,
    lobby_payload,
    player_payload,
    question_payload,
    question_summary,
    reveal_payload,
    sanitize_event_for_player,
    state_payload,
    team_payload,
)
from app.game.states import ANSWERABLE_STATES, JOINABLE_STATES, GameState, can_transition
from app.models.game import Answer, GameSession, Player, Team
from app.models.quiz import Question
from app.models.user import User

logger = logging.getLogger(__name__)


class GameEngine:
    """Live, server-authoritative state for a single game PIN."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        game_id: int,
        pin: str,
        quiz_id: int,
        quiz_title: str,
        host_id: int,
        host_name: str,
        mode: str,
        state: GameState,
        questions: list[QuizQuestion],
        players: list[LivePlayer],
        teams: list[LiveTeam],
        created_at: datetime,
        started_at: datetime | None,
        current_question_index: int,
        question_started_at: datetime | None,
        question_ends_at: datetime | None,
        connection_manager: ConnectionManager | None = None,
        scorer: ScoringStrategy | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.id = game_id
        self.pin = pin
        self.quiz_id = quiz_id
        self.quiz_title = quiz_title
        self.host_id = host_id
        self.host_name = host_name
        self.mode = mode
        self.state = state
        self.questions: list[QuizQuestion] = questions
        self.created_at = created_at
        self.started_at = started_at
        self.ended_at: datetime | None = None
        self.current_question_index = current_question_index
        self.question_started_at = question_started_at
        self.question_ends_at = question_ends_at

        self.players: dict[int, LivePlayer] = {p.id: p for p in players}
        self.teams: dict[int, LiveTeam] = {t.id: t for t in teams}
        #: answers for the *current* question only: player_id -> record
        self.answered: dict[int, AnswerRecord] = {}

        self.lock = asyncio.Lock()
        self.manager = connection_manager or default_manager
        self.scorer: ScoringStrategy = scorer or scoring_service
        self._timer_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------ helpers
    @property
    def current_question(self) -> QuizQuestion | None:
        if 0 <= self.current_question_index < len(self.questions):
            return self.questions[self.current_question_index]
        return None

    @property
    def has_more_questions(self) -> bool:
        return self.current_question_index + 1 < len(self.questions)

    @property
    def is_terminal(self) -> bool:
        return self.state in (GameState.FINISHED, GameState.CANCELLED)

    def can_start(self) -> bool:
        return self.state == GameState.LOBBY and bool(self.players) and bool(self.questions)

    def time_remaining_ms(self) -> int | None:
        """Milliseconds until the authoritative deadline (0 once passed)."""
        if self.state != GameState.QUESTION_ACTIVE or self.question_ends_at is None:
            return None
        return max(0, ms_between(utcnow(), as_utc(self.question_ends_at)))

    def connected_player_ids(self) -> set[int]:
        return {p.id for p in self.players.values() if p.connected}

    def _transition(self, target: GameState) -> None:
        """The *only* place ``self.state`` is assigned."""
        if self.state == target:
            return
        if not can_transition(self.state, target):
            raise GameError(
                GameErrorCode.INVALID_STATE_TRANSITION,
                f"Cannot move from {self.state.value} to {target.value}.",
            )
        logger.info("game %s: %s -> %s", self.pin, self.state.value, target.value)
        self.state = target

    def _require_host(self, actor_user_id: int | None) -> None:
        if actor_user_id is None or int(actor_user_id) != int(self.host_id):
            raise GameError(
                GameErrorCode.UNAUTHORIZED_HOST,
                "Only the host of this game can perform that action.",
                status_code=403,
            )

    def _require_live(self) -> None:
        if self.state == GameState.CANCELLED:
            raise GameError(GameErrorCode.GAME_CANCELLED)
        if self.state == GameState.FINISHED:
            raise GameError(GameErrorCode.GAME_ENDED)

    async def _persist(self, **overrides: Any) -> None:
        """Write the runtime fields through to the ``game_sessions`` row."""
        async with self.session_factory() as session:
            row = await session.get(GameSession, self.id)
            if row is None:  # pragma: no cover - defensive
                return
            row.status = self.state.value
            row.current_question_index = self.current_question_index
            row.question_started_at = self.question_started_at
            row.question_ends_at = self.question_ends_at
            row.started_at = self.started_at
            row.ended_at = self.ended_at or row.ended_at
            for key, value in overrides.items():
                setattr(row, key, value)
            await session.commit()

    # ------------------------------------------------------- construction
    @classmethod
    async def load(
        cls,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
        pin: str,
        *,
        connection_manager: ConnectionManager | None = None,
        scorer: ScoringStrategy | None = None,
    ) -> "GameEngine":
        """Build (or rebuild) an engine for ``pin`` from persisted state."""
        game = await session.scalar(select(GameSession).where(GameSession.game_pin == pin))
        if game is None:
            raise GameError(GameErrorCode.GAME_NOT_FOUND)

        question_rows = (
            await session.scalars(
                select(Question)
                .where(Question.quiz_id == game.quiz_id)
                .order_by(Question.order_index, Question.id)
            )
        ).all()
        questions = [
            QuizQuestion(
                id=q.id,
                order_index=q.order_index,
                text=q.question_text,
                options=list(q.options or []),
                correct_answer=q.correct_answer,
                explanation=q.explanation,
                time_limit=q.time_limit or settings.default_time_limit,
                points=q.points if q.points is not None else settings.default_points,
            )
            for q in question_rows
        ]

        player_rows = (
            await session.scalars(select(Player).where(Player.game_id == game.id))
        ).all()
        team_rows = (
            await session.scalars(select(Team).where(Team.game_id == game.id))
        ).all()
        host = await session.get(User, game.host_id)

        team_members: dict[int, list[int]] = {}
        for row in player_rows:
            if row.team_id is not None:
                team_members.setdefault(row.team_id, []).append(row.id)

        engine = cls(
            session_factory=session_factory,
            game_id=game.id,
            pin=game.game_pin,
            quiz_id=game.quiz_id,
            quiz_title=game.quiz.title if game.quiz else "Quiz",
            host_id=game.host_id,
            host_name=host.name if host else "Host",
            mode=game.mode,
            state=GameState(game.status),
            questions=questions,
            players=[
                LivePlayer(
                    id=p.id,
                    nickname=p.nickname,
                    score=p.score,
                    # nobody is connected until a socket actually attaches
                    connected=False,
                    team_id=p.team_id,
                    user_id=p.user_id,
                    joined_at=as_utc(p.joined_at) or utcnow(),
                )
                for p in player_rows
            ],
            teams=[
                LiveTeam(
                    id=t.id,
                    name=t.name,
                    score=t.score,
                    created_at=as_utc(t.created_at) or utcnow(),
                    member_ids=sorted(team_members.get(t.id, [])),
                )
                for t in team_rows
            ],
            created_at=as_utc(game.created_at) or utcnow(),
            started_at=as_utc(game.started_at),
            current_question_index=game.current_question_index,
            question_started_at=as_utc(game.question_started_at),
            question_ends_at=as_utc(game.question_ends_at),
            connection_manager=connection_manager,
            scorer=scorer,
        )
        await engine._rehydrate_current_answers(session)
        return engine

    async def _rehydrate_current_answers(self, session: AsyncSession) -> None:
        """Restore "who already answered" for the question in progress.

        This is what makes both a player reconnect *and* a full server restart
        non-destructive: a player who answered 3 seconds before a crash is not
        allowed to answer again afterwards.
        """
        self.answered.clear()
        question = self.current_question
        if question is None or self.state == GameState.LOBBY:
            return
        rows = (
            await session.scalars(
                select(Answer).where(
                    Answer.game_id == self.id, Answer.question_id == question.id
                )
            )
        ).all()
        for row in rows:
            self.answered[row.player_id] = AnswerRecord(
                player_id=row.player_id,
                question_id=row.question_id,
                selected_answer=row.selected_answer,
                is_correct=row.is_correct,
                response_time_ms=row.response_time_ms,
                points_awarded=row.points_awarded,
                submitted_at=as_utc(row.submitted_at) or utcnow(),
            )

    async def resume_timer_if_needed(self) -> None:
        """Re-arm the authoritative timer after a hydration."""
        if self.state != GameState.QUESTION_ACTIVE or self.question_ends_at is None:
            return
        if ms_between(utcnow(), as_utc(self.question_ends_at)) <= 0:
            # the question should already be over - close it out now
            await self.finalize_current_question("timer-resume")
        else:
            self._arm_timer(self.current_question_index, self.question_ends_at)

    # ---------------------------------------------------------- broadcast
    async def _emit(
        self,
        event_type: WSEventType | str,
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> int:
        return await self.manager.broadcast(self.pin, event_type, payload, **kwargs)

    async def broadcast_lobby_state(
        self, event_type: WSEventType, extra: dict[str, Any] | None = None
    ) -> None:
        """Roster events always carry a full lobby snapshot.

        Shipping the whole (tiny) snapshot with each event removes an entire
        class of client-side merge bugs - the client simply replaces its lobby.
        """
        payload: dict[str, Any] = {"lobby": lobby_payload(self)}
        if extra:
            payload.update(extra)
        await self._emit(event_type, payload)

    # ------------------------------------------------------------- roster
    def _reindex_teams(self) -> None:
        """Keep ``LiveTeam.member_ids`` consistent with the players' team_id."""
        for team in self.teams.values():
            team.member_ids = []
        for player in self.players.values():
            if player.team_id is not None and player.team_id in self.teams:
                self.teams[player.team_id].member_ids.append(player.id)
        for team in self.teams.values():
            team.member_ids.sort()

    def team_member_ids(self, team_id: int) -> list[int]:
        team = self.teams.get(team_id)
        return list(team.member_ids) if team else []

    def team_member_count(self, team_id: int) -> int:
        return len(self.team_member_ids(team_id))

    def is_team_full(self, team_id: int) -> bool:
        return self.team_member_count(team_id) >= settings.max_team_size

    def teamless_player_ids(self) -> list[int]:
        return [p.id for p in self.players.values() if p.team_id is None]

    async def register_player(self, row: Player, *, broadcast: bool = True) -> LivePlayer:
        """Add an already-persisted player to the live roster."""
        player = LivePlayer(
            id=row.id,
            nickname=row.nickname,
            score=row.score,
            connected=False,
            team_id=row.team_id,
            user_id=row.user_id,
            joined_at=as_utc(row.joined_at) or utcnow(),
        )
        async with self.lock:
            self.players[player.id] = player
            self._reindex_teams()
        if broadcast:
            await self.broadcast_lobby_state(
                WSEventType.PLAYER_JOINED, {"player": player_payload(player, self)}
            )
        return player

    async def remove_player(self, player_id: int, *, broadcast: bool = True) -> None:
        async with self.lock:
            player = self.players.pop(player_id, None)
            self.answered.pop(player_id, None)
            self._reindex_teams()
        if broadcast and player is not None:
            await self.broadcast_lobby_state(
                WSEventType.PLAYER_LEFT, {"player": player_payload(player, self)}
            )

    async def set_player_connected(
        self, player_id: int, connected: bool, *, broadcast: bool = False
    ) -> LivePlayer | None:
        """Flip the presence flag.  Used by the socket layer on connect/close."""
        async with self.lock:
            player = self.players.get(player_id)
            if player is None:
                return None
            changed = player.connected != connected
            player.connected = connected
            if not changed or not broadcast:
                return player
        await self.broadcast_lobby_state(
            WSEventType.PLAYER_UPDATED, {"player": player_payload(player, self)}
        )
        return player

    async def register_team(self, row: Team, *, broadcast: bool = True) -> LiveTeam:
        team = LiveTeam(
            id=row.id,
            name=row.name,
            score=row.score,
            created_at=as_utc(row.created_at) or utcnow(),
        )
        async with self.lock:
            self.teams[team.id] = team
            self._reindex_teams()
        if broadcast:
            await self.broadcast_lobby_state(
                WSEventType.TEAM_CREATED, {"team": team_payload(team, self)}
            )
        return team

    def apply_team_assignment(self, player_id: int, team_id: int | None) -> None:
        """Memory-only roster update.

        The caller must hold ``self.lock`` (so the capacity check is atomic
        with the update) and must already have committed the ``players`` row.
        """
        player = self.players.get(player_id)
        if player is None:
            raise GameError(GameErrorCode.PLAYER_NOT_IN_GAME)
        if team_id is not None and team_id not in self.teams:
            raise GameError(GameErrorCode.TEAM_NOT_FOUND)
        player.team_id = team_id
        self._reindex_teams()

    async def notify_team_updated(self, team_id: int) -> None:
        team = self.teams.get(team_id)
        if team is None:
            return
        await self.broadcast_lobby_state(
            WSEventType.TEAM_UPDATED, {"team": team_payload(team, self)}
        )

    # ----------------------------------------------------------- snapshot
    def snapshot(self, *, for_player_id: int | None = None) -> dict[str, Any]:
        # state_payload now handles role-aware serialization internally.
        return state_payload(self, for_player_id=for_player_id)

    # ------------------------------------------------------- host: start
    async def start_game(self, actor_user_id: int | None) -> None:
        async with self.lock:
            self._require_host(actor_user_id)
            if self.state != GameState.LOBBY:
                raise GameError(GameErrorCode.GAME_ALREADY_ACTIVE)
            if not self.questions:
                raise GameError(GameErrorCode.NO_QUESTIONS)
            if not self.players:
                raise GameError(GameErrorCode.NO_PLAYERS)
            self.started_at = utcnow()
            await self._persist()
            await self._emit(
                WSEventType.GAME_STARTED,
                {
                    "gameId": self.id,
                    "gamePin": self.pin,
                    "mode": self.mode,
                    "startedAt": iso(self.started_at),
                    "totalQuestions": len(self.questions),
                    "questions": [question_summary(q) for q in self.questions],
                    "lobby": lobby_payload(self),
                },
            )
            await self._start_question_locked(0)

    # ----------------------------------------------------- the question
    async def _start_question_locked(self, index: int) -> None:
        """Open question ``index``.  Caller must hold ``self.lock``."""
        if not 0 <= index < len(self.questions):
            await self._finish_locked("completed")
            return
        self._cancel_timer()
        question = self.questions[index]
        self.current_question_index = index
        # a fresh question means a fresh answer set
        self.answered = {}
        now = utcnow()
        self.question_started_at = now
        self.question_ends_at = now + timedelta(seconds=question.time_limit)
        self._transition(GameState.QUESTION_ACTIVE)
        await self._persist()
        await self._emit(WSEventType.QUESTION_STARTED, question_payload(self))
        self._arm_timer(index, self.question_ends_at)

    def _arm_timer(self, index: int, ends_at: datetime) -> None:
        self._cancel_timer()
        self._timer_task = asyncio.create_task(
            self._question_timer(index, ends_at),
            name=f"playoot-timer:{self.pin}:{index}",
        )

    def _cancel_timer(self) -> None:
        task = self._timer_task
        self._timer_task = None
        if task is None or task.done():
            return
        # `_finalize_locked` is also reached FROM the timer task itself (the
        # clock ran out).  Cancelling `asyncio.current_task()` would throw a
        # CancelledError into the very coroutine that is closing the question,
        # aborting it before QUESTION_ENDED is ever broadcast - which strands
        # every client in a half-revealed state.  Detach the reference (done
        # above) and let the running task wind down on its own; when the caller
        # is a different task (host advance, early close, teardown) the sleeping
        # timer still has to be cancelled.
        if task is not asyncio.current_task():
            task.cancel()

    async def _question_timer(self, index: int, ends_at: datetime) -> None:
        """The authority on when a question is over - not the client."""
        try:
            delay = max(0.0, (as_utc(ends_at) - utcnow()).total_seconds())
            if delay:
                await asyncio.sleep(delay)
            await self.finalize_current_question("timer", expected_index=index)
        except asyncio.CancelledError:  # pragma: no cover - normal on early close
            raise
        except Exception:
            logger.exception("question timer failed for game %s q%s", self.pin, index)

    # ---------------------------------------------------- closing a question
    async def finalize_current_question(
        self, reason: str = "timer", *, expected_index: int | None = None
    ) -> bool:
        """Close the live question.  Safe to call from the timer, an answer
        handler or a host command - it is idempotent and never double-fires."""
        async with self.lock:
            if self.state != GameState.QUESTION_ACTIVE:
                return False
            if (
                expected_index is not None
                and expected_index != self.current_question_index
            ):
                return False
            await self._finalize_locked(reason)
            return True

    async def _finalize_locked(self, reason: str) -> None:
        """QUESTION_ACTIVE -> QUESTION_REVEAL -> LEADERBOARD, broadcasting both."""
        self._cancel_timer()
        question = self.current_question
        self._transition(GameState.QUESTION_REVEAL)
        await self._persist()
        await self._emit(
            WSEventType.QUESTION_ENDED,
            {
                "reason": reason,
                "questionId": str(question.id) if question else None,
                "questionNumber": self.current_question_index + 1,
                "totalQuestions": len(self.questions),
                "reveal": reveal_payload(self),
                "leaderboard": leaderboard_payload(self),
                "hasMoreQuestions": self.has_more_questions,
                "state": self.state.value,
            },
        )
        await self._sync_team_scores()
        self._transition(GameState.LEADERBOARD)
        await self._persist()
        await self._emit(
            WSEventType.LEADERBOARD_UPDATED,
            {
                "leaderboard": leaderboard_payload(self),
                "reveal": reveal_payload(self),
                "hasMoreQuestions": self.has_more_questions,
                "state": self.state.value,
            },
        )

    async def _sync_team_scores(self) -> None:
        """Recompute and persist team totals via the centralised strategy."""
        member_scores: dict[int, list[int]] = {}
        for player in self.players.values():
            if player.team_id is not None:
                member_scores.setdefault(player.team_id, []).append(player.score)
        for team in self.teams.values():
            team.score = team_scoring_service.aggregate(member_scores.get(team.id, []))
        if not self.teams:
            return
        async with self.session_factory() as session:
            for team in self.teams.values():
                row = await session.get(Team, team.id)
                if row is not None:
                    row.score = team.score
            await session.commit()

    def _all_connected_answered(self) -> bool:
        """Everyone currently connected has answered, so the question may close
        early instead of burning the rest of the clock."""
        if not self.answered:
            return False
        connected = self.connected_player_ids()
        if not connected:
            return False
        return connected.issubset(set(self.answered))

    # --------------------------------------------------- host: advance
    async def next_question(self, actor_user_id: int | None) -> None:
        async with self.lock:
            self._require_host(actor_user_id)
            if self.state == GameState.LOBBY:
                raise GameError(
                    GameErrorCode.GAME_NOT_ACTIVE, "Start the game before advancing."
                )
            if self.state == GameState.QUESTION_ACTIVE:
                # advancing mid-question is the same as closing it early
                await self._finalize_locked("host-advance")
            if self.state == GameState.QUESTION_REVEAL:
                await self._sync_team_scores()
                self._transition(GameState.LEADERBOARD)
                await self._persist()
            if not self.has_more_questions:
                await self._finish_locked("completed")
                return
            next_index = self.current_question_index + 1
            await self._emit(
                WSEventType.NEXT_QUESTION,
                {
                    "nextQuestionIndex": next_index,
                    "nextQuestionNumber": next_index + 1,
                    "totalQuestions": len(self.questions),
                },
            )
            await self._start_question_locked(next_index)

    # ------------------------------------------------------ host: end
    async def end_game(self, actor_user_id: int | None) -> None:
        async with self.lock:
            self._require_host(actor_user_id)
            if self.is_terminal:
                return
            await self._finish_locked("host-ended")

    async def cancel_game(self, actor_user_id: int | None) -> None:
        async with self.lock:
            self._require_host(actor_user_id)
            if self.state == GameState.CANCELLED:
                return
            if self.state == GameState.FINISHED:
                raise GameError(GameErrorCode.GAME_ENDED)
            await self._finish_locked("host-cancelled", cancelled=True)

    async def _finish_locked(self, reason: str, *, cancelled: bool = False) -> None:
        self._cancel_timer()
        self.ended_at = utcnow()
        await self._sync_team_scores()
        if cancelled:
            self._transition(GameState.CANCELLED)
            await self._persist()
            await self._emit(
                WSEventType.GAME_CANCELLED,
                {
                    "gameId": self.id,
                    "gamePin": self.pin,
                    "reason": reason,
                    "cancelledAt": iso(self.ended_at),
                },
            )
            return
        self._transition(GameState.FINISHED)
        await self._persist()
        await self._emit(
            WSEventType.GAME_FINISHED,
            {
                "gameId": self.id,
                "gamePin": self.pin,
                "mode": self.mode,
                "reason": reason,
                "endedAt": iso(self.ended_at),
                "totalQuestions": len(self.questions),
                "playerCount": len(self.players),
                "leaderboard": leaderboard_payload(self),
                "finalLeaderboard": leaderboard_payload(self),
            },
        )

    # ------------------------------------------------------ player: answer
    async def submit_answer(
        self, *, player_id: int, question_id: str | int, answer_index: Any
    ) -> AnswerRecord:
        """Validate, grade and record one answer.  Fully server-side."""
        async with self.lock:
            self._require_live()
            player = self.players.get(player_id)
            if player is None:
                raise GameError(GameErrorCode.PLAYER_NOT_IN_GAME)
            if self.state not in ANSWERABLE_STATES:
                raise GameError(GameErrorCode.NO_ACTIVE_QUESTION)
            question = self.current_question
            if question is None:
                raise GameError(GameErrorCode.NO_ACTIVE_QUESTION)
            if str(question_id) != str(question.id):
                raise GameError(
                    GameErrorCode.QUESTION_MISMATCH,
                    "That answer was submitted for a different question.",
                    details={"activeQuestionId": str(question.id)},
                )
            # duplicate submissions are rejected before anything else
            if player_id in self.answered:
                raise GameError(
                    GameErrorCode.ALREADY_ANSWERED,
                    "You have already answered this question.",
                    details={"questionId": str(question.id)},
                )
            try:
                index = int(answer_index)
            except (TypeError, ValueError):
                raise GameError(GameErrorCode.INVALID_ANSWER) from None
            if not 0 <= index < len(question.options):
                raise GameError(
                    GameErrorCode.INVALID_ANSWER,
                    f"Answer must be an option index between 0 and {len(question.options) - 1}.",
                    details={"optionCount": len(question.options)},
                )
            now = utcnow()
            ends_at = as_utc(self.question_ends_at)
            deadline_ms = int(ends_at.timestamp() * 1000) + settings.answer_grace_ms
            if int(now.timestamp() * 1000) > deadline_ms:
                raise GameError(
                    GameErrorCode.QUESTION_EXPIRED,
                    "Time ran out for that question.",
                    details={"endsAt": iso(ends_at)},
                )
            started_at = as_utc(self.question_started_at) or now
            response_time_ms = max(
                0, min(ms_between(started_at, now), question.time_limit * 1000)
            )
            grade = self.scorer.grade(
                is_correct=index == question.correct_index,
                response_time_ms=response_time_ms,
                time_limit_seconds=question.time_limit,
                base_points=question.points,
            )
            record = AnswerRecord(
                player_id=player_id,
                question_id=question.id,
                selected_answer=index,
                is_correct=grade.is_correct,
                response_time_ms=grade.response_time_ms,
                points_awarded=grade.points_awarded,
                submitted_at=now,
            )
            # the unique constraint on (game, question, player) is the final
            # backstop if two submissions ever raced past the check above
            async with self.session_factory() as session:
                session.add(
                    Answer(
                        game_id=self.id,
                        question_id=question.id,
                        player_id=player_id,
                        selected_answer=index,
                        is_correct=grade.is_correct,
                        response_time_ms=grade.response_time_ms,
                        points_awarded=grade.points_awarded,
                        submitted_at=now,
                    )
                )
                row = await session.get(Player, player_id)
                if row is not None:
                    row.score = int(row.score or 0) + grade.points_awarded
                await session.commit()

            self.answered[player_id] = record
            player.score += grade.points_awarded

            answered_count = len(self.answered)
            player_count = len(self.players)
            # private acknowledgement - correctness stays hidden while live
            await self.manager.send_to_player(
                player_id,
                WSEventType.ANSWER_SUBMITTED,
                {
                    "questionId": str(question.id),
                    "accepted": True,
                    "selectedAnswer": index,
                    "responseTimeMs": grade.response_time_ms,
                    "answeredCount": answered_count,
                    "playerCount": player_count,
                },
            )
            await self._emit(
                WSEventType.PLAYER_ANSWERED,
                {
                    "questionId": str(question.id),
                    "playerId": player_id,
                    "nickname": player.nickname,
                    "answeredCount": answered_count,
                    "playerCount": player_count,
                },
                exclude_player_id=player_id,
            )
            if self._all_connected_answered():
                await self._finalize_locked("all-answered")
            return record