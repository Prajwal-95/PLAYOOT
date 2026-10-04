"""Engine-level authority checks.

These drive :class:`~app.game.engine.GameEngine` directly so the timer, the
deadline grace window and concurrent submissions can be tested precisely.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from app.config import settings
from app.core.timeutil import utcnow
from app.game.errors import GameError, GameErrorCode
from app.game.registry import get_registry
from conftest import join


async def _engine(game: dict):
    return await get_registry().get(game["game_pin"])


async def _started(game: dict, host: dict):
    """Hydrate the engine with the joined players, then start the game."""
    engine = await _engine(game)
    await engine.start_game(host["user"]["id"])
    return engine


def _code(excinfo) -> str:
    return excinfo.value.code.value


# ------------------------------------------------------------------ authority
async def test_engine_refuses_a_non_host(client, game, host, other_host):
    join(client, game, "Ada")
    engine = await _engine(game)
    with pytest.raises(GameError) as excinfo:
        await engine.start_game(other_host["user"]["id"])
    assert _code(excinfo) == GameErrorCode.UNAUTHORIZED_HOST.value


async def test_engine_cannot_start_without_players(client, game, host):
    engine = await _engine(game)
    with pytest.raises(GameError) as excinfo:
        await engine.start_game(host["user"]["id"])
    assert _code(excinfo) == GameErrorCode.NO_PLAYERS.value


async def test_engine_rejects_answer_before_the_game_starts(client, game, host):
    session = join(client, game, "Ada")
    engine = await _engine(game)
    with pytest.raises(GameError) as excinfo:
        await engine.submit_answer(
            player_id=session["player"]["player_id"], question_id="1", answer_index=0
        )
    assert _code(excinfo) == GameErrorCode.NO_ACTIVE_QUESTION.value


async def test_engine_rejects_answer_from_a_stranger(client, game, host):
    join(client, game, "Ada")
    engine = await _started(game, host)
    with pytest.raises(GameError) as excinfo:
        await engine.submit_answer(player_id=999_999, question_id="1", answer_index=0)
    assert _code(excinfo) == GameErrorCode.PLAYER_NOT_IN_GAME.value


# ------------------------------------------------------------- the deadline
async def test_answer_after_the_deadline_is_rejected(client, game, host):
    session = join(client, game, "Ada")
    engine = await _started(game, host)
    question = engine.current_question
    engine.question_ends_at = utcnow() - timedelta(seconds=5)  # deadline in the past
    engine._cancel_timer()
    with pytest.raises(GameError) as excinfo:
        await engine.submit_answer(
            player_id=session["player"]["player_id"],
            question_id=question.id,
            answer_index=0,
        )
    assert _code(excinfo) == GameErrorCode.QUESTION_EXPIRED.value


async def test_answer_inside_the_grace_window_is_accepted(client, game, host):
    """A few hundred ms of network jitter must not lose a legitimate answer."""
    session = join(client, game, "Ada")
    engine = await _started(game, host)
    question = engine.current_question
    engine.question_ends_at = utcnow() - timedelta(milliseconds=settings.answer_grace_ms / 2)
    engine._cancel_timer()
    record = await engine.submit_answer(
        player_id=session["player"]["player_id"], question_id=question.id, answer_index=0
    )
    assert record.is_correct is True


async def test_answer_outside_a_zero_grace_window_is_rejected(client, game, host, monkeypatch):
    session = join(client, game, "Ada")
    engine = await _started(game, host)
    question = engine.current_question
    monkeypatch.setattr(settings, "answer_grace_ms", 0)
    engine.question_ends_at = utcnow() - timedelta(milliseconds=200)
    engine._cancel_timer()
    with pytest.raises(GameError) as excinfo:
        await engine.submit_answer(
            player_id=session["player"]["player_id"],
            question_id=question.id,
            answer_index=0,
        )
    assert _code(excinfo) == GameErrorCode.QUESTION_EXPIRED.value


# ------------------------------------------------------------ simultaneous
async def test_simultaneous_answers_are_each_recorded_once(client, game, host):
    ada = join(client, game, "Ada")
    bob = join(client, game, "Bob")
    engine = await _started(game, host)
    question = engine.current_question

    results = await asyncio.gather(
        engine.submit_answer(
            player_id=ada["player"]["player_id"], question_id=question.id, answer_index=0
        ),
        engine.submit_answer(
            player_id=bob["player"]["player_id"], question_id=question.id, answer_index=0
        ),
        return_exceptions=True,
    )
    assert not any(isinstance(r, GameError) for r in results), results
    assert len(engine.answered) == 2
    assert all(r.is_correct for r in results)


async def test_same_player_racing_themselves_records_one_answer(client, game, host):
    ada = join(client, game, "Ada")
    join(client, game, "Bob")  # keeps the question open
    engine = await _started(game, host)
    question = engine.current_question

    results = await asyncio.gather(
        *[
            engine.submit_answer(
                player_id=ada["player"]["player_id"],
                question_id=question.id,
                answer_index=0,
            )
            for _ in range(4)
        ],
        return_exceptions=True,
    )
    accepted = [r for r in results if not isinstance(r, GameError)]
    rejected = [r for r in results if isinstance(r, GameError)]
    assert len(accepted) == 1
    assert all(r.code is GameErrorCode.ALREADY_ANSWERED for r in rejected)
    assert len(engine.answered) == 1


# -------------------------------------------------------------------- timer
async def test_authoritative_timer_closes_the_question(client, game, host):
    """The server's own clock ends the question - never the client."""
    join(client, game, "Ada")
    engine = await _started(game, host)
    assert engine.state.value == "QUESTION_ACTIVE"

    engine.question_ends_at = utcnow() + timedelta(milliseconds=300)
    engine._arm_timer(engine.current_question_index, engine.question_ends_at)

    await asyncio.sleep(1.0)
    assert engine.state.value in {"QUESTION_REVEAL", "LEADERBOARD"}
    assert engine.time_remaining_ms() in (None, 0)


async def test_time_remaining_counts_down(client, game, host):
    join(client, game, "Ada")
    engine = await _started(game, host)
    first = engine.time_remaining_ms()
    assert first is not None and 0 < first <= 5_000
    await asyncio.sleep(0.3)
    second = engine.time_remaining_ms()
    assert second is not None and second < first


# ------------------------------------------------------------------- ending
async def test_engine_finishes_after_the_last_question(client, game, host):
    join(client, game, "Ada")
    engine = await _started(game, host)
    assert engine.has_more_questions is True
    await engine.next_question(host["user"]["id"])
    assert engine.current_question_index == 1
    await engine.next_question(host["user"]["id"])
    assert engine.state.value == "FINISHED"


async def test_no_answers_after_the_game_is_finished(client, game, host):
    session = join(client, game, "Ada")
    engine = await _started(game, host)
    question_id = engine.current_question.id
    await engine.cancel_game(host["user"]["id"])
    with pytest.raises(GameError):
        await engine.submit_answer(
            player_id=session["player"]["player_id"],
            question_id=question_id,
            answer_index=0,
        )
    assert engine.state.value == "CANCELLED"