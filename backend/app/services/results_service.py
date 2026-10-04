"""Final results and analytics.

Computed from the database, not from memory, so results survive restarts and
can be re-read at any time after a game ends.  Ranks come from the same
deterministic :func:`app.game.scoring.ranking` used by the live leaderboard.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pin import normalise_pin
from app.core.timeutil import iso, utcnow
from app.game.errors import GameError, GameErrorCode
from app.game.scoring import ranking, team_scoring_service
from app.models.game import Answer, GameSession, Player, Team
from app.models.quiz import Question


async def build_results(session: AsyncSession, *, pin: str) -> dict[str, Any]:
    game = await session.scalar(
        select(GameSession).where(GameSession.game_pin == normalise_pin(pin))
    )
    if game is None:
        raise GameError(GameErrorCode.GAME_NOT_FOUND)

    questions = (
        await session.scalars(
            select(Question)
            .where(Question.quiz_id == game.quiz_id)
            .order_by(Question.order_index, Question.id)
        )
    ).all()
    players = (
        await session.scalars(
            select(Player).where(Player.game_id == game.id).order_by(Player.joined_at, Player.id)
        )
    ).all()
    teams = (
        await session.scalars(
            select(Team).where(Team.game_id == game.id).order_by(Team.created_at, Team.id)
        )
    ).all()
    answers = (await session.scalars(select(Answer).where(Answer.game_id == game.id))).all()

    answers_by_player: dict[int, list[Answer]] = defaultdict(list)
    answers_by_question: dict[int, list[Answer]] = defaultdict(list)
    for row in answers:
        answers_by_player[row.player_id].append(row)
        answers_by_question[row.question_id].append(row)

    team_names = {t.id: t.name for t in teams}

    # --------------------------------------------------------- individuals
    individual: list[dict[str, Any]] = []
    for player in players:
        rows = answers_by_player.get(player.id, [])
        answered = len(rows)
        correct = sum(1 for r in rows if r.is_correct)
        individual.append(
            {
                "id": player.id,
                "playerId": player.id,
                "name": player.nickname,
                "score": player.score,
                "correct": correct,
                "incorrect": answered - correct,
                "answered": answered,
                "unanswered": max(0, len(questions) - answered),
                "accuracy": round(correct / answered, 4) if answered else 0.0,
                "avgResponseTimeMs": (
                    int(sum(r.response_time_ms for r in rows) / answered) if answered else 0
                ),
                "teamId": player.team_id,
                "teamName": team_names.get(player.team_id) if player.team_id else None,
                "_order_key": iso(player.joined_at) or "",
            }
        )
    individual = ranking(individual, score_key="score")
# --------------------------------------------------------------- teams
    team_entries: list[dict[str, Any]] = []
    for team in teams:
        member_rows = [p for p in players if p.team_id == team.id]
        team_entries.append(
            {
                "id": team.id,
                "teamId": team.id,
                "name": team.name,
                "score": team_scoring_service.aggregate([p.score for p in member_rows]),
                "memberCount": len(member_rows),
                "members": [
                    {"playerId": p.id, "nickname": p.nickname, "score": p.score}
                    for p in member_rows
                ],
                "_order_key": iso(team.created_at) or "",
            }
        )
    team_entries = ranking(team_entries, score_key="score")

    # --------------------------------------------------------- per question
    question_stats: list[dict[str, Any]] = []
    for question in questions:
        rows = answers_by_question.get(question.id, [])
        distribution = [0] * len(question.options)
        for row in rows:
            if 0 <= row.selected_answer < len(distribution):
                distribution[row.selected_answer] += 1
        question_stats.append(
            {
                "questionId": question.id,
                "questionNumber": question.order_index + 1,
                "questionText": question.question_text,
                "options": list(question.options),
                "correctIndex": question.correct_index,
                "correctAnswer": question.correct_answer,
                "explanation": question.explanation,
                "distribution": distribution,
                "answeredCount": len(rows),
                "correctCount": sum(1 for r in rows if r.is_correct),
            }
        )

    total_answers = len(answers)
    total_correct = sum(1 for r in answers if r.is_correct)
    return {
        "game": {
            "gameId": game.id,
            "gamePin": game.game_pin,
            "quizId": game.quiz_id,
            "quizTitle": game.quiz.title if game.quiz else "Quiz",
            "mode": game.mode,
            "status": game.status,
            "createdAt": iso(game.created_at),
            "startedAt": iso(game.started_at),
            "endedAt": iso(game.ended_at),
            "questionCount": len(questions),
            "playerCount": len(players),
            "teamCount": len(teams),
        },
        "individualLeaderboard": individual,
        "teamLeaderboard": team_entries,
        "questions": question_stats,
        "stats": {
            "totalAnswers": total_answers,
            "totalCorrect": total_correct,
            "accuracy": round(total_correct / total_answers, 4) if total_answers else 0.0,
            "playerCount": len(players),
            "questionCount": len(questions),
        },
        "serverTime": iso(utcnow()),
    }