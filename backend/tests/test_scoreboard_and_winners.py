"""The host scoreboard and the final winner reveal.

Two halves:

* **source guards** - the host stage must drive its Next Question control from
  a sticky top bar, animate only figures the backend already computed, offer
  the winner selection manually, reveal the final ranks bottom-to-top and
  clamp the podium to the authoritative ``winnersCount``.  Both stages must
  share the same four option shapes.
* **WebSocket checks** - the payload the animation is fed with: the host's
  ``QUESTION_ENDED`` reveal carries the per-player results, and the host's
  state/finish snapshots carry ``winnersCount``.

React never scores anything: it only arranges and animates backend values.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import join

BACKEND_DIR = Path(__file__).resolve().parents[1]
FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


# ===========================================================================
# helpers
# ===========================================================================
def recv_until(ws, wanted, limit: int = 60):
    wanted = {wanted} if isinstance(wanted, str) else set(wanted)
    seen = []
    for _ in range(limit):
        message = ws.receive_json()
        seen.append(message["type"])
        if message["type"] in wanted:
            return message
    raise AssertionError(f"never received {wanted}; saw {seen}")


def send(ws, action: str, payload: dict | None = None) -> None:
    ws.send_json({"type": action, "payload": payload or {}})


def _src(relpath: str) -> str:
    path = FRONTEND_SRC / relpath
    if not path.exists():
        pytest.skip("frontend sources are not available in this checkout")
    return path.read_text(encoding="utf-8")


def _panel() -> str:
    return _src("components/game/HostGamePanel.tsx")


def _play() -> str:
    return _src("pages/PlayPage.tsx")


# ===========================================================================
# 1. Next Question - sticky, at the TOP, only when another question exists
# ===========================================================================
def test_next_question_lives_in_a_single_sticky_top_bar():
    source = _panel()

    assert source.count("onClick={onNextQuestion}") == 1, (
        "there must be exactly one Next Question control"
    )
    assert source.count("Next Question") == 1, (
        "a second Next Question affordance would break the sticky-top rule"
    )

    bar = re.search(
        r"\{showNextQuestionBar &&\s*\(\s*<div className=\{cn\(\"sticky z-30 py-2\","
        r"\s*stickyOffset\)\}>",
        source,
    )
    assert bar, "the progression control must sit inside a sticky top bar"

    # ...and it is rendered ABOVE the scoreboard, never below it.
    button_at = source.index("onClick={onNextQuestion}")
    scoreboard_at = source.index("Question scoreboard")
    assert button_at < scoreboard_at, (
        "Next Question must be above the scoreboard so it is never scrolled to"
    )


def test_next_question_only_appears_when_another_question_follows():
    source = _panel()

    gate = re.search(
        r"const showNextQuestionBar\s*=\s*"
        r"isReveal\s*&&\s*!isFinalResults\s*&&\s*hasMoreQuestions",
        source,
    )
    assert gate, (
        "Next Question must be gated on: reveal state, not final results, "
        "and another question actually existing"
    )
    assert "&& hasMoreQuestions" in source


def test_the_sticky_offset_is_configurable_for_both_headers():
    source = _panel()
    assert "stickyOffset" in source
    assert 'stickyOffset = "top-16"' in source, (
        "the default docks under the h-16 app-shell nav"
    )

    lobby = _src("pages/HostLobbyPage.tsx")
    play = _play()
    assert 'stickyOffset="top-16"' in lobby
    assert 'stickyOffset="top-14"' in play, (
        "the /play host stage draws its own h-14 header"
    )


# ===========================================================================
# 2. Per-question scoreboard - authoritative values only
# ===========================================================================
def test_the_scoreboard_shows_every_required_column():
    source = _panel()

    for field in (
        "pointsAwarded",   # +points this question
        "responseTimeMs",  # response time
        "isCorrect",       # correct / incorrect
        "totalScore",      # cumulative count-up target
        "rank",            # rank
    ):
        assert field in source, f"scoreboard is missing `{field}`"

    assert "reveal?.results" in source, "rows must come from the reveal payload"
    assert "leaderboard?.entries" in source, "rank must come from the leaderboard"
    assert "<CountUp" in source, "the cumulative total must count up"
    assert "Question scoreboard" in source
    # Non-responders still get a row so the board accounts for everyone.
    assert "nonResponders" in source


def test_the_scoreboard_never_computes_a_score_in_react():
    source = _panel()
    code = "\n".join(
        line
        for line in source.splitlines()
        if not line.strip().startswith(("//", "*", "/*"))
    )

    for forbidden in (
        "scorer",
        "grade(",
        "base_points",
        "bonus",
        "penalty",
        "score +=",
        "points +=",
        "score =",
        "points =",
        "pointsAwarded =",
        "totalScore =",
        "correct_index",
    ):
        assert forbidden not in code, (
            f"React must not score anything - found `{forbidden}`"
        )

    # The figures are read straight off the payload objects.
    assert "pointsAwarded: r.pointsAwarded" in code
    assert "totalScore: r.totalScore" in code
    assert "responseTimeMs: r.responseTimeMs" in code
    assert "isCorrect: r.isCorrect" in code


def test_the_count_up_is_an_animation_not_a_recalculation():
    source = _panel()
    assert "requestAnimationFrame" in source
    # It interpolates between the previous and the new backend total.
    assert re.search(r"from=\{row\.totalScore\s*-\s*row\.pointsAwarded\}", source)
    assert re.search(r"to=\{row\.totalScore\}", source)


# ===========================================================================
# 3. Final results - manual select, staggered reveal, clamped podium
# ===========================================================================
def test_select_winners_is_manual_and_never_auto():
    source = _panel()

    assert "Select Winners" in source
    assert source.count('setFinalPhase("reveal")') == 1, (
        "the reveal must be triggered from exactly one place"
    )
    assert source.count("onClick={startWinnerReveal}") == 1

    reveal_at = source.index('setFinalPhase("reveal")')
    handler_at = source.index("const startWinnerReveal")
    assert handler_at < reveal_at, (
        "`setFinalPhase(\"reveal\")` must live inside the click handler, "
        "so nothing can auto-select the winners"
    )
    # No other phase advance happens on a timer started outside the click.
    assert 'setFinalPhase("board")' in source, (
        "the flow must reset when a new final result arrives"
    )
    assert re.search(
        r"useEffect\(\(\) => \{\s*clearFinalTimers\(\);\s*setFinalPhase\(\"board\"\);"
        r".*?\}, \[isFinalResults",
        source,
        re.DOTALL,
    ), "the final flow must reset whenever the final results change"


def test_the_complete_leaderboard_is_shown_before_any_reveal():
    source = _panel()

    board_first = source.index('finalPhase === "board"')
    reveal_block = source.index('finalPhase === "reveal"')
    winners_block = source.index('finalPhase === "winners"')
    assert board_first < reveal_block < winners_block

    # Every participant is listed, not just the winners.
    assert "Final leaderboard" in source
    assert "finalEntries" in source


def test_the_rank_reveal_runs_bottom_to_top_with_a_stagger():
    source = _panel()

    assert "finalEntries.slice().reverse()" in source, (
        "the champion must be revealed LAST"
    )
    assert re.search(r"position \* 0\.22", source), "rows must be staggered"
    assert "scale: 0.85" in source and "y: 60" in source, (
        "rows should slide up / scale in"
    )
    assert 'finalPhase === "suspense"' in source, "a suspense beat is required"
    assert "And the winner is" in source or "Top" in source


def test_the_podium_is_built_from_the_authoritative_winners_count():
    source = _panel()

    assert "winnersCount" in source, "podium size comes from the backend"
    assert re.search(
        r"const winnerCount = Math\.min\(\s*"
        r"Math\.max\(winnersCount \|\| 3, 1\),\s*"
        r"finalEntries\.length\s*\)",
        source,
    ), "the podium must be clamped to the real participant count"
    assert "finalEntries.slice(0, winnerCount)" in source, (
        "never render more slots than the authoritative count"
    )
    # The rendered podium is filtered down to the entries that really exist.
    assert re.search(
        r"podiumOrder\s*\.filter\(\(index\) => index < winners\.length\)", source
    ), "a podium slot must never be fabricated for a participant who is absent"


def test_host_pages_pass_the_authoritative_winners_count_through():
    lobby = _src("pages/HostLobbyPage.tsx")
    play = _play()
    assert "winnersCount" in lobby
    assert "winnersCount" in play
    assert "winnersCount={winnersCount ?? 3}" in lobby
    assert "winnersCount={winnersCount ?? 3}" in play


# ===========================================================================
# 4. Shared option shapes on both stages
# ===========================================================================
def test_both_stages_use_the_shared_option_shapes():
    styles = _src("components/game/optionStyles.ts")
    host = _panel()
    play = _play()

    assert "OPTION_STYLES" in styles
    for shape in ("Triangle", "Circle", "Square", "Diamond"):
        assert f"Shape: {shape}," in styles, f"{shape} must be one of the four icons"

    # Kahoot's four tiles, in wire order.
    tiles = re.findall(r'tile: "bg-(\w+)-', styles)
    assert tiles == ["rose", "sky", "amber", "emerald"], (
        f"option tiles must be rose/sky/amber/emerald, got {tiles}"
    )

    assert 'from "./optionStyles"' in host
    assert 'from "../components/game/optionStyles"' in play
    assert "OPTION_STYLES[index % OPTION_STYLES.length]" in host
    assert "OPTION_STYLES[index % OPTION_STYLES.length]" in play

    # lucide glyphs, not emoji stand-ins.
    for source in (host, play):
        for glyph in ("▲", "●", "■", "◆"):
            assert glyph not in source, "option shapes must come from lucide"
        assert "lucide-react" in source


# ===========================================================================
# 5. The payload the animation is fed with
# ===========================================================================
def test_host_question_ended_carries_the_authoritative_reveal(client, host, game):
    """The scoreboard reads `reveal.results` - the backend must send it."""
    pin = game["game_pin"]
    session = join(client, game, "Ada")

    with client.websocket_connect(f"/ws/game/{pin}?token={host['token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={session['player_token']}"
        ) as player_ws:
            player_ws.receive_json()

            send(host_ws, "START_GAME")
            recv_until(host_ws, "GAME_STARTED")
            q1 = recv_until(host_ws, "QUESTION_STARTED")["payload"]

            send(
                player_ws,
                "SUBMIT_ANSWER",
                {"questionId": q1["questionId"], "answer": 0},
            )
            recv_until(player_ws, "ANSWER_SUBMITTED")

            ended = recv_until(host_ws, "QUESTION_ENDED")["payload"]
            assert ended["questionId"] == q1["questionId"]

            reveal = ended["reveal"]
            results = reveal["results"]
            assert len(results) == 1, "every responder must appear on the board"

            row = results[0]
            for field in (
                "playerId",
                "nickname",
                "selectedAnswer",
                "isCorrect",
                "responseTimeMs",
                "pointsAwarded",
                "totalScore",
            ):
                assert field in row, f"reveal result missing `{field}`"

            assert row["nickname"] == "Ada"
            assert row["isCorrect"] is True
            assert row["selectedAnswer"] == 0
            assert row["pointsAwarded"] > 0
            assert row["responseTimeMs"] >= 0
            assert row["totalScore"] == row["pointsAwarded"], (
                "the cumulative total must be the backend's own figure"
            )

            # Rank comes from the leaderboard broadcast, also backend-owned.
            board = recv_until(host_ws, "LEADERBOARD_UPDATED")["payload"]
            entry = board["leaderboard"]["entries"][0]
            assert entry["rank"] == 1
            assert entry["score"] == row["totalScore"]

            # drain the player socket so the room is idle at teardown
            send(player_ws, "PING")
            recv_until(player_ws, "PONG")


def test_host_state_and_finish_carry_the_authoritative_winners_count(
    client, host, game
):
    pin = game["game_pin"]
    # The engine refuses to start an empty room, so seat somebody first -
    # no player socket is opened, the host snapshot is all we care about here.
    join(client, game, "Ada")

    with client.websocket_connect(f"/ws/game/{pin}?token={host['token']}") as ws:
        ws.receive_json()

        send(ws, "REQUEST_STATE")
        sync = recv_until(ws, "STATE_SYNC")["payload"]
        assert sync.get("winnersCount") in (1, 3, 5, 10), (
            "a refreshed host must know how many podium slots to offer"
        )

        send(ws, "START_GAME")
        recv_until(ws, "QUESTION_STARTED")
        send(ws, "END_GAME")
        finished = recv_until(ws, "GAME_FINISHED")["payload"]

        assert finished["winnersCount"] == sync["winnersCount"]
        assert "finalLeaderboard" in finished
        entries = finished["finalLeaderboard"]["entries"]
        assert [e["name"] for e in entries] == ["Ada"]
        assert entries[0]["rank"] == 1
        assert finished["reason"] == "host-ended"
