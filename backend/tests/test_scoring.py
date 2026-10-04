"""Scoring maths and ranking - the server owns every number."""

from __future__ import annotations

import pytest

from app.game.scoring import (
    SpeedScoringService,
    TeamScoringService,
    ranking,
)


@pytest.fixture
def scorer():
    return SpeedScoringService()


# ------------------------------------------------------------------ correctness
def test_wrong_answer_scores_zero(scorer):
    grade = scorer.grade(
        is_correct=False,
        response_time_ms=10,
        time_limit_seconds=20,
        base_points=1000,
    )
    assert grade.is_correct is False
    assert grade.points_awarded == 0
    assert grade.speed_multiplier == 0.0


# -------------------------------------------------------------------- speed band
def test_instant_correct_answer_earns_full_points(scorer):
    grade = scorer.grade(
        is_correct=True,
        response_time_ms=0,
        time_limit_seconds=20,
        base_points=1000,
    )
    assert grade.points_awarded == 1000
    assert grade.speed_multiplier == 1.0


def test_last_moment_correct_answer_earns_half(scorer):
    grade = scorer.grade(
        is_correct=True,
        response_time_ms=20_000,
        time_limit_seconds=20,
        base_points=1000,
    )
    assert grade.points_awarded == 500
    assert grade.speed_multiplier == 0.5


def test_speed_bonus_decays_linearly(scorer):
    half = scorer.grade(
        is_correct=True,
        response_time_ms=10_000,
        time_limit_seconds=20,
        base_points=1000,
    )
    assert half.points_awarded == 750


def test_answers_cannot_exceed_base_points(scorer):
    # a client claiming a negative response time must not inflate the score
    grade = scorer.grade(
        is_correct=True,
        response_time_ms=-5_000,
        time_limit_seconds=20,
        base_points=1000,
    )
    assert grade.points_awarded == 1000
    assert grade.response_time_ms == 0


def test_response_time_is_capped_at_the_time_limit(scorer):
    slow = scorer.grade(
        is_correct=True,
        response_time_ms=999_999,
        time_limit_seconds=20,
        base_points=1000,
    )
    assert slow.points_awarded == 500


def test_zero_base_points_is_allowed(scorer):
    grade = scorer.grade(
        is_correct=True, response_time_ms=0, time_limit_seconds=20, base_points=0
    )
    assert grade.points_awarded == 0


def test_invalid_multiplier_bounds_are_rejected():
    with pytest.raises(ValueError):
        SpeedScoringService(min_multiplier=-1.0, max_multiplier=1.0)
    with pytest.raises(ValueError):
        SpeedScoringService(min_multiplier=0.9, max_multiplier=0.1)


# ----------------------------------------------------------------------- teams
def test_team_score_is_the_sum_of_members():
    assert TeamScoringService().aggregate([100, 250, 0, 50]) == 400


def test_team_score_ignores_negatives():
    assert TeamScoringService().aggregate([100, -50, 25]) == 125


# --------------------------------------------------------------------- ranking
def test_ranking_sorts_by_score_descending():
    ordered = ranking(
        [
            {"id": 1, "name": "low", "score": 10, "_order_key": "a"},
            {"id": 2, "name": "high", "score": 90, "_order_key": "b"},
            {"id": 3, "name": "mid", "score": 50, "_order_key": "c"},
        ]
    )
    assert [entry["name"] for entry in ordered] == ["high", "mid", "low"]
    assert [entry["rank"] for entry in ordered] == [1, 2, 3]


def test_tied_scores_share_a_rank_and_then_skip():
    ordered = ranking(
        [
            {"id": 1, "name": "a", "score": 100, "_order_key": "1"},
            {"id": 2, "name": "b", "score": 100, "_order_key": "2"},
            {"id": 3, "name": "c", "score": 50, "_order_key": "3"},
        ]
    )
    assert [entry["rank"] for entry in ordered] == [1, 1, 3]


def test_ranking_is_deterministic_for_ties():
    entries = [
        {"id": 2, "name": "b", "score": 100, "_order_key": "1"},
        {"id": 1, "name": "a", "score": 100, "_order_key": "1"},
    ]
    first = ranking(list(entries))
    second = ranking(list(reversed(entries)))
    assert [e["id"] for e in first] == [e["id"] for e in second]


def test_ranking_strips_internal_order_keys():
    ordered = ranking([{"id": 1, "name": "a", "score": 1, "_order_key": "x"}])
    assert "_order_key" not in ordered[0]