"""Deterministic, speed-based scoring.

The entire formula lives here so it can be tuned (or swapped for a
normalised/streak-aware scheme) without touching the game engine.

Individual score::

    points = base_points * multiplier
    multiplier = 0.5 + 0.5 * (time_remaining / time_limit)     # correct answer
    points = 0                                                # wrong answer

The multiplier is clamped to ``[0.5, 1.0]`` so a correct answer is always worth
at least half the question's base points and never more than all of them.
``base_points`` comes from ``Question.points`` (default 1000).

The awarded value is persisted on the ``Answer`` row, which means re-running the
leaderboard later can never change a historical result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

#: Slowest possible correct answer still earns this share of the base points.
MIN_SPEED_MULTIPLIER = 0.5
MAX_SPEED_MULTIPLIER = 1.0


@dataclass(frozen=True)
class AnswerGrade:
    is_correct: bool
    points_awarded: int
    response_time_ms: int
    speed_multiplier: float


class ScoringStrategy(Protocol):
    """Swap point for a different formula without touching the engine."""

    def grade(
        self,
        *,
        is_correct: bool,
        response_time_ms: int,
        time_limit_seconds: int,
        base_points: int,
    ) -> AnswerGrade: ...


class SpeedScoringService:
    """The MVP strategy: linear decay from ``base`` down to ``base / 2``."""

    def __init__(
        self,
        *,
        min_multiplier: float = MIN_SPEED_MULTIPLIER,
        max_multiplier: float = MAX_SPEED_MULTIPLIER,
    ) -> None:
        if not 0.0 <= min_multiplier <= max_multiplier:
            raise ValueError("min_multiplier must be between 0 and max_multiplier")
        self.min_multiplier = min_multiplier
        self.max_multiplier = max_multiplier

    def speed_multiplier(self, response_time_ms: int, time_limit_seconds: int) -> float:
        limit_ms = max(1, int(time_limit_seconds) * 1000)
        elapsed = max(0, min(int(response_time_ms), limit_ms))
        remaining_ratio = (limit_ms - elapsed) / limit_ms
        span = self.max_multiplier - self.min_multiplier
        return round(self.min_multiplier + span * remaining_ratio, 6)

    def grade(
        self,
        *,
        is_correct: bool,
        response_time_ms: int,
        time_limit_seconds: int,
        base_points: int,
    ) -> AnswerGrade:
        response_time_ms = max(0, int(response_time_ms))
        base_points = max(0, int(base_points))
        if not is_correct:
            return AnswerGrade(
                is_correct=False,
                points_awarded=0,
                response_time_ms=response_time_ms,
                speed_multiplier=0.0,
            )
        multiplier = self.speed_multiplier(response_time_ms, time_limit_seconds)
        return AnswerGrade(
            is_correct=True,
            points_awarded=int(round(base_points * multiplier)),
            response_time_ms=response_time_ms,
            speed_multiplier=multiplier,
        )


class TeamScoringService:
    """Aggregates individual scores into a team score.

    MVP rule::

        team_score = sum(member_scores)

    Kept behind a method so a later switch to average-of-members or a
    member-count-normalised score is a one-line change here rather than an
    engine rewrite.  Players who are not on a team simply do not contribute.
    """

    def aggregate(self, member_scores: Sequence[int]) -> int:
        return int(sum(max(0, int(s)) for s in member_scores))


#: Process-wide defaults.  The engine reads these; tests may inject their own.
scoring_service: ScoringStrategy = SpeedScoringService()
team_scoring_service = TeamScoringService()


def ranking(entries: Sequence[dict], *, score_key: str = "score") -> list[dict]:
    """Competition ranking with a deterministic tie-break.

    Sort order: score desc, then the caller-supplied ``order_key`` (joined_at /
    created_at ascending - "who got there first"), then ``id`` ascending.  That
    total order makes the output stable across processes and restarts.

    Tied scores share a rank; the next distinct score jumps the rank number
    (1, 2, 2, 4), which matches how a quiz leaderboard is expected to read.
    """
    ordered = sorted(
        entries,
        key=lambda e: (
            -int(e.get(score_key, 0)),
            e.get("_order_key") or "",
            int(e.get("id", 0)),
        ),
    )
    result: list[dict] = []
    previous_score: int | None = None
    previous_rank = 0
    for position, entry in enumerate(ordered, start=1):
        score = int(entry.get(score_key, 0))
        if previous_score is None or score != previous_score:
            previous_rank = position
            previous_score = score
        clean = {k: v for k, v in entry.items() if not k.startswith("_")}
        clean["rank"] = previous_rank
        result.append(clean)
    return result