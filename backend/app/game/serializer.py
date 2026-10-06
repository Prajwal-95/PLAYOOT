"""Payload builders - the single chokepoint for everything sent to clients.

Rules enforced *only* here:

* ``correct_answer`` / ``correct_index`` are absent from
  :func:`question_payload`, so they physically cannot leak during a live
  question.  They appear exclusively in :func:`reveal_payload`, which is sent
  after the question has closed.
* answer *selections* of other players are never broadcast while a question is
  active; only the fact that they answered.
* no ORM object is ever returned directly - every response is an explicit dict.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.config import settings
from app.core.timeutil import as_utc, iso, utcnow
from app.game.live import LivePlayer, LiveTeam, QuizQuestion
from app.game.scoring import ranking, team_scoring_service

if TYPE_CHECKING:  # pragma: no cover
    from app.game.engine import GameEngine


# --------------------------------------------------------------------- quiz
def question_summary(question: QuizQuestion) -> dict[str, Any]:
    return {
        "questionId": str(question.id),
        "questionNumber": question.order_index + 1,
        "timeLimit": question.time_limit,
        "points": question.points,
        "optionCount": len(question.options),
    }


# ---------------------------------------------------------------- gameplay
def question_payload(engine: "GameEngine") -> dict[str, Any] | None:
    """The QUESTION_STARTED payload.  Contains NO correct answer."""
    question = engine.current_question
    if question is None:
        return None
    now = utcnow()
    return {
        "questionId": str(question.id),
        "questionNumber": question.order_index + 1,
        "totalQuestions": len(engine.questions),
        "question": question.text,
        "options": list(question.options),
        "startedAt": iso(engine.question_started_at),
        "endsAt": iso(as_utc(engine.question_ends_at)),
        "timeLimit": question.time_limit,
        "points": question.points,
        "timeRemainingMs": engine.time_remaining_ms(),
        # lets the client correct for clock skew instead of trusting its own clock
        "serverTime": iso(now),
    }


def reveal_payload(engine: "GameEngine") -> dict[str, Any] | None:
    """Sent after the question closes - the first point at which the answer
    may be disclosed."""
    question = engine.current_question
    if question is None:
        return None
    records = engine.answered
    distribution = [0] * len(question.options)
    for record in records.values():
        if 0 <= record.selected_answer < len(distribution):
            distribution[record.selected_answer] += 1

    results: list[dict[str, Any]] = []
    for record in records.values():
        player = engine.players.get(record.player_id)
        results.append(
            {
                "playerId": record.player_id,
                "nickname": player.nickname if player else "Unknown",
                "teamId": player.team_id if player else None,
                "selectedAnswer": record.selected_answer,
                "isCorrect": record.is_correct,
                "responseTimeMs": record.response_time_ms,
                "pointsAwarded": record.points_awarded,
                "totalScore": player.score if player else 0,
            }
        )
    results.sort(key=lambda r: (-int(r["pointsAwarded"]), int(r["responseTimeMs"])))

    return {
        "questionId": str(question.id),
        "questionNumber": question.order_index + 1,
        "totalQuestions": len(engine.questions),
        "correctIndex": question.correct_index,
        "correctAnswer": question.correct_answer,
        "explanation": question.explanation,
        "distribution": distribution,
        "answeredCount": len(records),
        "playerCount": len(engine.players),
        "results": results,
        "revealedAt": iso(utcnow()),
    }


# ----------------------------------------------------------------- players
def _team_name(engine: "GameEngine", team_id: int | None) -> str | None:
    if team_id is None:
        return None
    team = engine.teams.get(team_id)
    return team.name if team else None


def player_payload(player: LivePlayer, engine: "GameEngine") -> dict[str, Any]:
    """Full player payload including score - for host only."""
    return {
        "playerId": player.id,
        "nickname": player.nickname,
        "score": player.score,
        "connected": player.connected,
        "teamId": player.team_id,
        "teamName": _team_name(engine, player.team_id),
        "joinedAt": iso(player.joined_at),
        "hasAnswered": player.id in engine.answered,
    }


def player_payload_safe(player: LivePlayer, engine: "GameEngine") -> dict[str, Any]:
    """Player payload WITHOUT real score (score=0) - for player sockets."""
    return {
        "playerId": player.id,
        "nickname": player.nickname,
        "score": 0,
        "connected": player.connected,
        "teamId": player.team_id,
        "teamName": _team_name(engine, player.team_id),
        "joinedAt": iso(player.joined_at),
        "hasAnswered": player.id in engine.answered,
    }


def team_payload(team: LiveTeam, engine: "GameEngine") -> dict[str, Any]:
    """Full team payload including score and member scores - for host only."""
    return {
        "teamId": team.id,
        "name": team.name,
        "score": team.score,
        "memberCount": team.member_count,
        "maxSize": settings.max_team_size,
        "isFull": team.member_count >= settings.max_team_size,
        "members": [
            player_payload(engine.players[pid], engine)
            for pid in team.member_ids
            if pid in engine.players
        ],
        "createdAt": iso(team.created_at),
    }


def team_payload_safe(team: LiveTeam, engine: "GameEngine") -> dict[str, Any]:
    """Team payload WITHOUT score and WITHOUT member scores - for player sockets."""
    return {
        "teamId": team.id,
        "name": team.name,
        "score": 0,
        "memberCount": team.member_count,
        "maxSize": settings.max_team_size,
        "isFull": team.member_count >= settings.max_team_size,
        "members": [
            player_payload_safe(engine.players[pid], engine)
            for pid in team.member_ids
            if pid in engine.players
        ],
        "createdAt": iso(team.created_at),
    }


def lobby_payload(engine: "GameEngine") -> dict[str, Any]:
    teamless = [p for p in engine.players.values() if p.team_id is None]
    return {
        "gameId": engine.id,
        "gamePin": engine.pin,
        "mode": engine.mode,
        "state": engine.state.value,
        "hostId": engine.host_id,
        "hostName": engine.host_name,
        "quiz": {
            "quizId": engine.quiz_id,
            "title": engine.quiz_title,
            "questionCount": len(engine.questions),
        },
        "players": [
            player_payload(p, engine)
            for p in sorted(
                engine.players.values(), key=lambda p: (iso(p.joined_at) or "", p.id)
            )
        ],
        "teams": [
            team_payload(t, engine)
            for t in sorted(
                engine.teams.values(), key=lambda t: (iso(t.created_at) or "", t.id)
            )
        ],
        "teamlessPlayers": [p.id for p in teamless],
        "maxTeamSize": settings.max_team_size,
        "counts": {
            "players": len(engine.players),
            "teams": len(engine.teams),
            "connectedPlayers": sum(1 for p in engine.players.values() if p.connected),
            "answeredCurrent": len(engine.answered),
        },
        "canStart": engine.can_start(),
        "serverTime": iso(utcnow()),
    }


def _compute_team_stats(engine: "GameEngine", team_id: int) -> dict[str, Any]:
    """Compute team statistics including response times, correct/incorrect counts."""
    team = engine.teams.get(team_id)
    if not team:
        return {
            "avgResponseTimeMs": 0,
            "correctAnswers": 0,
            "incorrectAnswers": 0,
            "totalAnswers": 0,
        }
    
    member_ids = [pid for pid in team.member_ids if pid in engine.players]
    if not member_ids:
        return {
            "avgResponseTimeMs": 0,
            "correctAnswers": 0,
            "incorrectAnswers": 0,
            "totalAnswers": 0,
        }
    
    # Get all answer records for this team's members
    correct = 0
    incorrect = 0
    total_response_ms = 0
    answered_count = 0
    
    for record in engine.answered.values():
        if record.player_id in member_ids:
            answered_count += 1
            total_response_ms += record.response_time_ms
            if record.is_correct:
                correct += 1
            else:
                incorrect += 1
    
    avg_response_ms = int(total_response_ms / answered_count) if answered_count > 0 else 0
    
    return {
        "avgResponseTimeMs": avg_response_ms,
        "correctAnswers": correct,
        "incorrectAnswers": incorrect,
        "totalAnswers": answered_count,
    }


def leaderboard_payload(engine: "GameEngine") -> dict[str, Any]:
    if engine.mode == "team":
        entries: list[dict[str, Any]] = []
        for team in engine.teams.values():
            member_scores = [
                engine.players[pid].score for pid in team.member_ids if pid in engine.players
            ]
            # Compute team stats (response time, correct/incorrect)
            team_stats = _compute_team_stats(engine, team.id)
            
            entries.append(
                {
                    "id": team.id,
                    "teamId": team.id,
                    "name": team.name,
                    "score": team_scoring_service.aggregate(member_scores),
                    "memberCount": len(member_scores),
                    "memberIds": list(team.member_ids),
                    # New fields for enhanced leaderboard
                    "avgResponseTimeMs": team_stats["avgResponseTimeMs"],
                    "correctAnswers": team_stats["correctAnswers"],
                    "incorrectAnswers": team_stats["incorrectAnswers"],
                    "totalAnswers": team_stats["totalAnswers"],
                    "_order_key": iso(team.created_at) or "",
                }
            )
        ranked = ranking(entries, score_key="score")
        for entry in ranked:
            entry["members"] = [
                player_payload(engine.players[pid], engine)
                for pid in entry.get("memberIds", [])
                if pid in engine.players
            ]
            entry.pop("memberIds", None)
            entry.pop("_order_key", None)
        return {"mode": "team", "entries": ranked, "updatedAt": iso(utcnow())}

    entries = [
        {
            "id": player.id,
            "playerId": player.id,
            "name": player.nickname,
            "score": player.score,
            "teamId": player.team_id,
            "teamName": _team_name(engine, player.team_id),
            "connected": player.connected,
            "_order_key": iso(player.joined_at) or "",
        }
        for player in engine.players.values()
    ]
    ranked = ranking(entries, score_key="score")
    for entry in ranked:
        entry.pop("_order_key", None)
    return {"mode": "individual", "entries": ranked, "updatedAt": iso(utcnow())}


# -------------------------------------------------------------- full state
def state_payload(engine: "GameEngine", *, for_player_id: int | None) -> dict[str, Any]:
    """Complete snapshot used for the initial handshake and for reconnection.

    A reconnecting player gets their score, team, current question, the
    authoritative deadline and whether they already answered - all from the
    server, never from local storage.

    When `for_player_id` is provided, the payload is sanitized for a player socket:
    - No scores in player/team objects
    - No leaderboard
    - myResult excludes pointsAwarded
    - me excludes score
    """
    is_player = for_player_id is not None
    question = engine.current_question
    if question is None:
        current_question = None
    elif engine.state.value == "QUESTION_ACTIVE":
        current_question = question_payload(engine)
    else:
        # reveal / leaderboard: the answer is public now
        base = question_payload(engine) or {}
        current_question = {**base, "correctIndex": question.correct_index}

    already_answered = is_player and for_player_id in engine.answered
    my_result = None
    if is_player and already_answered:
        record = engine.answered[for_player_id]
        my_result = {
            "selectedAnswer": record.selected_answer,
            # correctness is withheld while the question is still live
            "isCorrect": (
                None if engine.state.value == "QUESTION_ACTIVE" else record.is_correct
            ),
            "responseTimeMs": record.response_time_ms,
            # pointsAwarded is never sent to players
        }

    me = None
    if is_player and for_player_id in engine.players:
        me = player_payload_safe(engine.players[for_player_id], engine)

    # Choose payload builders based on role
    player_builder = player_payload_safe if is_player else player_payload
    team_builder = team_payload_safe if is_player else team_payload

    return {
        "game": {
            "gameId": engine.id,
            "gamePin": engine.pin,
            "mode": engine.mode,
            "state": engine.state.value,
            "hostId": engine.host_id,
            "hostName": engine.host_name,
            "quizId": engine.quiz_id,
            "quizTitle": engine.quiz_title,
            "totalQuestions": len(engine.questions),
            "currentQuestionIndex": engine.current_question_index,
            "currentQuestionNumber": engine.current_question_index + 1,
            "createdAt": iso(engine.created_at),
            "startedAt": iso(engine.started_at),
        },
        "players": [
            player_builder(p, engine)
            for p in sorted(
                engine.players.values(), key=lambda p: (iso(p.joined_at) or "", p.id)
            )
        ],
        "teams": [
            team_builder(t, engine)
            for t in sorted(
                engine.teams.values(), key=lambda t: (iso(t.created_at) or "", t.id)
            )
        ],
        "currentQuestion": current_question,
        "reveal": (
            reveal_payload(engine)
            if engine.state.value in {"QUESTION_REVEAL", "LEADERBOARD"}
            else None
        ),
        "leaderboard": None if is_player else leaderboard_payload(engine),
        "timeRemainingMs": engine.time_remaining_ms(),
        "questionStartedAt": iso(engine.question_started_at),
        "questionEndsAt": iso(engine.question_ends_at),
        "alreadyAnswered": already_answered,
        "myResult": my_result,
        "me": me,
        "canStart": engine.can_start(),
        "serverTime": iso(utcnow()),
    }


def _player_safe_reveal(reveal: dict[str, Any] | None) -> dict[str, Any] | None:
    """Reveal for players: correct answer + distribution, no per-player scores."""
    if not isinstance(reveal, dict):
        return reveal
    safe = dict(reveal)
    # `results` carries totalScore/pointsAwarded per player - host only.
    safe.pop("results", None)
    return safe


def sanitize_event_for_player(
    event_type: str, payload: dict[str, Any] | None
) -> dict[str, Any] | None | bool:
    """Return the player-safe version of a broadcast payload.

    Returns ``False`` when the event should not be sent to players at all
    (leaderboard refreshes are host-only; players wait on the reveal).
    """
    if not isinstance(payload, dict):
        return payload
    if event_type == "LEADERBOARD_UPDATED":
        return False
    if event_type == "QUESTION_ENDED":
        safe = dict(payload)
        safe.pop("leaderboard", None)
        safe["reveal"] = _player_safe_reveal(payload.get("reveal"))
        return safe
    if event_type in ("GAME_FINISHED", "GAME_CANCELLED"):
        safe = dict(payload)
        safe.pop("leaderboard", None)
        safe.pop("finalLeaderboard", None)
        safe.pop("winnersCount", None)
        return safe
    if event_type in (
        "PLAYER_JOINED",
        "PLAYER_LEFT",
        "PLAYER_UPDATED",
        "TEAM_CREATED",
        "TEAM_JOINED",
        "TEAM_LEFT",
        "TEAM_UPDATED",
        "GAME_STARTED",
    ):
        lobby = payload.get("lobby")
        if isinstance(lobby, dict):
            safe = dict(payload)
            lobby_safe = dict(lobby)
            lobby_safe["players"] = [
                {**p, "score": 0} for p in lobby.get("players", []) or []
            ]
            teams_safe = []
            for t in lobby.get("teams", []) or []:
                tq = dict(t)
                tq["score"] = 0
                tq["members"] = [
                    {**m, "score": 0} for m in tq.get("members", []) or []
                ]
                teams_safe.append(tq)
            lobby_safe["teams"] = teams_safe
            safe["lobby"] = lobby_safe
            return safe
        return payload
    return payload