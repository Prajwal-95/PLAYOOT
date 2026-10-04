"""The single, centralised game state machine.

Every status change in the system goes through :meth:`GameEngine._transition`.
No React component, route handler or WebSocket branch sets a status directly.

    LOBBY
      -> QUESTION_ACTIVE     (host starts / host advances)
      -> QUESTION_REVEAL     (timer expired, everyone answered, or host ends it)
      -> LEADERBOARD         (automatic, immediately after the reveal)
      -> QUESTION_ACTIVE     (host advances to the next question)
      -> FINISHED            (no questions left, or host ends the game)
      -> CANCELLED           (host cancels - reachable from any live state)
"""

from __future__ import annotations

from enum import Enum


class GameState(str, Enum):
    LOBBY = "LOBBY"
    QUESTION_ACTIVE = "QUESTION_ACTIVE"
    QUESTION_REVEAL = "QUESTION_REVEAL"
    LEADERBOARD = "LEADERBOARD"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"

    def __str__(self) -> str:  # pragma: no cover
        return self.value


#: ``GameState`` values that are still "live" (a client may attach to them).
ACTIVE_STATES: frozenset[GameState] = frozenset(
    {
        GameState.LOBBY,
        GameState.QUESTION_ACTIVE,
        GameState.QUESTION_REVEAL,
        GameState.LEADERBOARD,
    }
)

TERMINAL_STATES: frozenset[GameState] = frozenset({GameState.FINISHED, GameState.CANCELLED})

#: A player may only take a seat while the game is in one of these states.
JOINABLE_STATES: frozenset[GameState] = frozenset({GameState.LOBBY})

#: The state in which the server will accept a SUBMIT_ANSWER action.
ANSWERABLE_STATES: frozenset[GameState] = frozenset({GameState.QUESTION_ACTIVE})

#: Explicit legal transitions.  Anything not listed here is a programming bug.
ALLOWED_TRANSITIONS: dict[GameState, frozenset[GameState]] = {
    GameState.LOBBY: frozenset(
        {GameState.QUESTION_ACTIVE, GameState.FINISHED, GameState.CANCELLED}
    ),
    GameState.QUESTION_ACTIVE: frozenset(
        {GameState.QUESTION_REVEAL, GameState.FINISHED, GameState.CANCELLED}
    ),
    GameState.QUESTION_REVEAL: frozenset(
        {GameState.LEADERBOARD, GameState.FINISHED, GameState.CANCELLED}
    ),
    GameState.LEADERBOARD: frozenset(
        {GameState.QUESTION_ACTIVE, GameState.FINISHED, GameState.CANCELLED}
    ),
    GameState.FINISHED: frozenset(),
    GameState.CANCELLED: frozenset(),
}


def can_transition(source: GameState, target: GameState) -> bool:
    return target in ALLOWED_TRANSITIONS.get(source, frozenset())


def next_state_after_leaderboard(*, has_more_questions: bool) -> GameState:
    return GameState.QUESTION_ACTIVE if has_more_questions else GameState.FINISHED