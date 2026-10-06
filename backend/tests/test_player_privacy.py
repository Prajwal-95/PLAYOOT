"""Score privacy: what a player socket is *allowed* to receive.

Players never see a score, a leaderboard, a ranking, the winner reveal or the
podium - so those fields must not reach their browser at all.  The stripping
happens in the serialiser and in the broadcast sanitizer; this file proves it
over a real WebSocket and then pins the player screen down at source level so
a future edit cannot reintroduce a hidden scoreboard behind CSS.

Role separation is asserted too: the interface is chosen by the authenticated
WebSocket ``role``, never by the device.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from conftest import join

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


def _code(relpath: str) -> str:
    """Source with comments removed, so prose cannot mask an assertion."""
    source = _src(relpath)
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line
        for line in source.splitlines()
        if not line.strip().startswith(("//", "*", "/*"))
    )


def _play() -> str:
    return _src("pages/PlayPage.tsx")


# ===========================================================================
# 1. Live payloads
# ===========================================================================
def test_player_state_sync_carries_no_leaderboard_and_no_winners_count(
    client, host, game
):
    pin = game["game_pin"]
    session = join(client, game, "Ada")

    with client.websocket_connect(
        f"/ws/game/{pin}?player_token={session['player_token']}"
    ) as ws:
        recv_until(ws, "CONNECTED")
        state = recv_until(ws, "STATE_SYNC")["payload"]

        # No leaderboard, ever.
        assert state["leaderboard"] is None
        # No podium size either - it is host-only, and omitted rather than null.
        assert "winnersCount" not in state, "players must not learn the podium size"
        # No reveal yet, and none would carry per-player figures anyway.
        assert state["reveal"] is None
        assert state["currentQuestion"] is None

        # Roster scores are zeroed for a player socket.
        assert state["players"][0]["score"] == 0
        assert state["me"]["score"] == 0
        assert state["myResult"] is None


def test_player_question_ended_carries_the_answer_but_not_the_scores(
    client, host, game
):
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

            # The player learns *what* was right, never *how much* it scored.
            ended = recv_until(player_ws, "QUESTION_ENDED")["payload"]
            reveal = ended["reveal"]
            assert "results" not in reveal, "per-player results are host-only"
            assert "leaderboard" not in ended or ended["leaderboard"] is None
            wire = json.dumps(ended)
            for leak in ("pointsAwarded", "totalScore", "winnersCount", "finalLeaderboard"):
                assert leak not in wire, f"QUESTION_ENDED leaked `{leak}` to a player"
            assert reveal["correctIndex"] == 0
            assert reveal["distribution"] == [1, 0, 0, 0]

            # The host, by contrast, gets the full breakdown.
            host_ended = recv_until(host_ws, "QUESTION_ENDED")["payload"]
            results = host_ended["reveal"]["results"]
            assert results, "the host scoreboard needs at least one row"
            assert "pointsAwarded" in results[0]
            assert "totalScore" in results[0]

            recv_until(host_ws, "LEADERBOARD_UPDATED")

            # A fresh snapshot after the round closes must stay equally quiet.
            send(player_ws, "REQUEST_STATE")
            frame = recv_until(
                player_ws, {"STATE_SYNC", "LEADERBOARD_UPDATED"}
            )
            assert frame["type"] == "STATE_SYNC", (
                "LEADERBOARD_UPDATED is host-only; players wait on the reveal"
            )
            state = frame["payload"]
            assert state["leaderboard"] is None
            assert "winnersCount" not in state
            assert "results" not in (state["reveal"] or {})
            assert state["players"][0]["score"] == 0
            if state["myResult"]:
                assert "pointsAwarded" not in state["myResult"]

            # leave the room idle before the sockets are torn down
            send(player_ws, "PING")
            recv_until(player_ws, "PONG")


def test_player_game_finished_has_no_final_leaderboard_and_no_winners_count(
    client, host, game
):
    pin = game["game_pin"]
    session = join(client, game, "Ada")

    with client.websocket_connect(f"/ws/game/{pin}?token={host['token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={session['player_token']}"
        ) as player_ws:
            player_ws.receive_json()

            send(host_ws, "START_GAME")
            recv_until(host_ws, "QUESTION_STARTED")

            send(host_ws, "END_GAME")
            finished = recv_until(player_ws, "GAME_FINISHED")["payload"]

            wire = json.dumps(finished)
            for leak in ("finalLeaderboard", "leaderboard", "winnersCount", "score"):
                assert leak not in wire, f"GAME_FINISHED leaked `{leak}` to a player"

            host_finished = recv_until(host_ws, "GAME_FINISHED")["payload"]
            assert "finalLeaderboard" in host_finished
            assert host_finished["winnersCount"] in (1, 3, 5, 10)

            send(player_ws, "PING")
            recv_until(player_ws, "PONG")


def test_a_player_socket_never_receives_a_score_bearing_event(client, host, game):
    """While a question is live, no frame may hand a player somebody's score."""
    pin = game["game_pin"]
    session = join(client, game, "Ada")
    other = join(client, game, "Zoe")

    with client.websocket_connect(f"/ws/game/{pin}?token={host['token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={session['player_token']}"
        ) as player_ws:
            player_ws.receive_json()
            with client.websocket_connect(
                f"/ws/game/{pin}?player_token={other['player_token']}"
            ) as other_ws:
                other_ws.receive_json()

                send(host_ws, "START_GAME")
                recv_until(host_ws, "QUESTION_STARTED")

                q1 = recv_until(player_ws, "QUESTION_STARTED")["payload"]
                send(
                    player_ws,
                    "SUBMIT_ANSWER",
                    {"questionId": q1["questionId"], "answer": 0},
                )
                recv_until(player_ws, "ANSWER_SUBMITTED")
                # Zoe does not answer, so the question stays open.

                send(player_ws, "PING")
                recv_until(player_ws, "PONG")

                send(other_ws, "PING")
                recv_until(other_ws, "PONG")

                # Host knows who answered; the live question payload itself
                # still hides the correct option.
                assert "correctIndex" not in q1
                assert "correctAnswer" not in q1
                assert "results" not in q1

                send(host_ws, "END_GAME")
                recv_until(player_ws, "GAME_FINISHED")
                recv_until(other_ws, "GAME_FINISHED")


# ===========================================================================
# 2. The player screen, at source level
# ===========================================================================
def _player_only() -> str:
    """PlayPage with the ``role === "host"`` branch excised.

    Whatever is left is everything a player can possibly be shown, so the
    score/ranking/winner guards run against the real surface instead of
    against a component the player never reaches.
    """
    source = _play()
    host_at = source.index('if (role === "host")')
    ui_at = source.index("const timeLimit = displayQuestion?.timeLimit")
    assert host_at < ui_at, "the host branch must precede the player stage"
    return source[:host_at] + source[ui_at:]


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line
        for line in source.splitlines()
        if not line.strip().startswith(("//", "*", "/*"))
    )


def test_the_player_screen_shows_no_score_or_ranking_ui():
    player = _player_only()
    code = _strip_comments(player)

    for forbidden in (
        "Select Winners",
        "Next Question",
        "WINNER",
        "Runner-up",
        "podium",
        "POINTS",
        "pointsAwarded",
        "totalScore",
        "{entry.score}",
        "{winner.score}",
        "{player.score}",
        "{me.score}",
        "leaderboard.entries",
        "finalLeaderboard",
        "winnersCount={",
        "{leaderboard",
        "<HostGamePanel",
        "rank",
    ):
        assert forbidden not in code, (
            f"the player screen must never show `{forbidden}`"
        )

    # Score values must not be interpolated anywhere in executable code.
    assert not re.search(r"\{[A-Za-z_.?]*score\}", code), (
        "a player screen must not render a score"
    )


def test_the_player_end_screen_is_the_quiet_terminus():
    source = _play()
    assert "QUIZ COMPLETE" in source
    assert "See the host for the final results" in source
    # No podium, no winner list, no points on the way out.
    for forbidden in ("Winner", "Runner-up", "POINTS", "score"):
        assert forbidden not in _player_finished_block(source), (
            f"the player end screen must not show `{forbidden}`"
        )


def _player_finished_block(source: str) -> str:
    """The FINISHED branch of PlayPage, comments and all stripped."""
    start = source.index("PLAYER END SCREEN")
    # start at the beginning of the comment line so it strips with the rest
    start = source.rfind("\n", 0, start) + 1
    end = source.index("Game Cancelled", start)
    block = source[start:end]
    block = re.sub(r"/\*.*?\*/", "", block, flags=re.DOTALL)
    return "\n".join(
        line
        for line in block.splitlines()
        if not line.strip().startswith(("//", "*", "/*"))
    )


def test_the_player_stage_never_renders_the_question_text():
    """Kept in sync with the equivalent guard in test_websocket_flow.py."""
    source = _play()
    for interpolation in (
        "{displayQuestion.question}",
        "{currentQuestion?.question}",
        "{question.question}",
    ):
        assert interpolation not in source


def test_the_interface_is_chosen_by_the_websocket_role_only():
    source = _play()
    code = _code("pages/PlayPage.tsx")

    # The host stage is gated on the authenticated role...
    assert re.search(r'if \(role === "host"\) \{', source)
    assert re.search(r'role !== "host"', source)

    # ...and nothing device-shaped decides anything.
    for device_signal in (
        "window.innerWidth",
        "window.innerHeight",
        "matchMedia",
        "navigator.userAgent",
        "useMediaQuery",
        "window.screen",
        "orientation",
        "ontouchstart",
        "maxWidth:",
        "breakpoint",
    ):
        assert device_signal not in code, (
            f"role separation must not depend on `{device_signal}`"
        )

    # The host-only panel is rendered strictly inside the host branch.
    host_branch = code.index('if (role === "host")')
    panel = code.index("<HostGamePanel")
    assert host_branch < panel, "the host stage must sit inside the role check"
    # ...and nothing after the host branch renders it again.
    assert "<HostGamePanel" not in _strip_comments(_player_only())


def test_the_role_comes_from_the_server_not_the_url_or_local_storage():
    source = _play()
    # `role` is destructured straight from the socket hook - the backend
    # assigned it at handshake time from the credential that was presented.
    assert re.search(r"const \{[^}]*\brole\b[^}]*\} = useGameSocket\(", source, re.DOTALL)
    assert 'localStorage.getItem("role")' not in source
    assert "sessionStorage" not in source
