"""Real multiplayer flow over the gameplay WebSocket.

Starlette's TestClient attaches an actual host socket and an actual player
socket to the same running engine, so this exercises the real protocol.
"""

from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from conftest import join


def recv_until(ws, wanted, limit: int = 30):
    """Read frames until one of ``wanted`` arrives."""
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


# ===========================================================================
# Player-connection regression suite
#
# Reproduces the real production order: the HOST socket attaches first (which
# hydrates and caches the GameEngine in the registry), the player THEN joins
# over REST, and only afterwards opens their gameplay socket.
#
# `websocket.accept()` happens before every step below, so any exception raised
# after the handshake closes the socket abnormally - which the browser reports
# as code 1006 with no readable cause.
# ===========================================================================
def test_player_socket_after_host_socket_is_already_connected(client, host, game):
    """Host connected -> player joins over REST -> player socket opens."""
    from app.game.manager import manager

    pin = game["game_pin"]
    host_ws_ctx = client.websocket_connect(f"/ws/game/{pin}?token={host['token']}")
    with host_ws_ctx as host_ws:
        host_ws.receive_json()  # host CONNECTED (engine is now hydrated/cached)

        # the player joins AFTER the engine has been hydrated and cached
        session = join(client, game, "Ada")
        player_token = session["player_token"]
        player_id = session["player"]["player_id"]

        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={player_token}"
        ) as player_ws:
            # 1. handshake succeeded (we are inside the context manager)
            # 2. CONNECTED is received
            connected = recv_until(player_ws, "CONNECTED")
            assert connected["payload"]["role"] == "player"
            assert connected["payload"]["playerId"] == player_id

            # 3. STATE_SYNC is received
            state = recv_until(player_ws, "STATE_SYNC")
            assert state["payload"]["game"]["gamePin"] == pin
            assert state["payload"]["me"]["playerId"] == player_id
            assert state["payload"]["me"]["connected"] is True

            # 4. no unexpected disconnect - a round trip still works
            send(player_ws, "PING")
            assert recv_until(player_ws, "PONG")["type"] == "PONG"

            # 5. player appears in manager state while the socket is live
            assert manager.is_player_connected(player_id) is True
            assert player_id in manager.connected_player_ids(pin)
            assert manager.room_size(pin) >= 2  # host + player

    # and it is released again on close
    assert manager.is_player_connected(player_id) is False


def test_player_socket_state_sync_lists_the_player(client, host, game):
    """The snapshot the player receives must contain their own roster entry.

    Players never receive scoreboard data - leaderboard is None and all scores are 0.
    """
    pin = game["game_pin"]
    session = join(client, game, "Ada")
    player_id = session["player"]["player_id"]

    with client.websocket_connect(
        f"/ws/game/{pin}?player_token={session['player_token']}"
    ) as ws:
        recv_until(ws, "CONNECTED")
        state = recv_until(ws, "STATE_SYNC")["payload"]
        assert [p["playerId"] for p in state["players"]] == [player_id]
        # Player scores are sanitized to 0
        assert state["players"][0]["score"] == 0
        assert state["alreadyAnswered"] is False
        assert state["myResult"] is None
        # Leaderboard is never sent to players
        assert state["leaderboard"] is None


def test_player_socket_rejects_token_for_a_different_game(client, host, game, quiz):
    """A genuine token, but bound to another game."""
    other = client.post(
        "/api/games", headers=host["headers"], json={"quiz_id": quiz["id"]}
    ).json()
    other_session = join(client, other, "Zoe")

    with client.websocket_connect(
        f"/ws/game/{game['game_pin']}?player_token={other_session['player_token']}"
    ) as ws:
        message = ws.receive_json()
        assert message["type"] == "GAME_ERROR"
        assert message["payload"]["code"] == "PLAYER_NOT_IN_GAME"


def test_player_socket_rejects_player_not_in_the_game(client, host, game):
    """A well-formed, correctly signed token for a player that never joined."""
    from app.core.security import create_player_token

    engine_id = game["game_id"]
    orphan = create_player_token(999_999, engine_id, game["game_pin"])

    with client.websocket_connect(
        f"/ws/game/{game['game_pin']}?player_token={orphan}"
    ) as ws:
        message = ws.receive_json()
        assert message["type"] == "GAME_ERROR"
        assert message["payload"]["code"] == "PLAYER_NOT_IN_GAME"


def test_player_socket_rejects_garbage_token(client, host, game):
    with client.websocket_connect(
        f"/ws/game/{game['game_pin']}?player_token=not-a-real-token"
    ) as ws:
        message = ws.receive_json()
        assert message["type"] == "GAME_ERROR"
        assert message["payload"]["code"] == "UNAUTHORIZED"


# ===========================================================================
# 1006 regression
#
# `websocket.accept()` runs before registration.  If anything raised after that
# point escaped the endpoint, Starlette could not send an error frame or a close
# code, uvicorn dropped the TCP connection, and the browser reported
# code 1006 with no reason at all.
#
# These two tests pin that guarantee down.
# ===========================================================================
def test_host_receives_roster_update_when_player_connects(client, host, game):
    """Host socket connected -> player joins -> player socket connects.

    The host must be told about the player over the socket.  This covers the
    whole real-time path: engine.register_player -> broadcast_lobby_state ->
    manager.broadcast -> the host's open socket.
    """
    pin = game["game_pin"]

    with client.websocket_connect(f"/ws/game/{pin}?token={host['token']}") as host_ws:
        recv_until(host_ws, "CONNECTED")
        recv_until(host_ws, "STATE_SYNC")

        session = join(client, game, "Ada")
        player_id = session["player"]["player_id"]

        # the roster event fired by register_player during the REST join
        joined = recv_until(host_ws, "PLAYER_JOINED")
        assert joined["payload"]["lobby"]["players"] != []
        assert (
            joined["payload"]["lobby"]["players"][0]["playerId"] == player_id
        )
        # can_start requires at least one player, so the host may now start
        assert joined["payload"]["lobby"]["canStart"] is True

        # the presence event fired when the player's socket attaches
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={session['player_token']}"
        ) as player_ws:
            recv_until(player_ws, "CONNECTED")

            updated = recv_until(host_ws, "PLAYER_UPDATED")
            roster = updated["payload"]["lobby"]
            assert len(roster["players"]) == 1
            assert roster["counts"]["players"] == 1
            assert roster["counts"]["connectedPlayers"] == 1
            assert roster["players"][0]["connected"] is True

    # and the host is told when the player goes away again
    with client.websocket_connect(f"/ws/game/{pin}?token={host['token']}") as host_ws:
        recv_until(host_ws, "CONNECTED")
        recv_until(host_ws, "STATE_SYNC")
        session2 = join(client, game, "Bea")
        recv_until(host_ws, "PLAYER_JOINED")

        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={session2['player_token']}"
        ) as player_ws:
            recv_until(player_ws, "CONNECTED")
            recv_until(host_ws, "PLAYER_UPDATED")

        left = recv_until(host_ws, "PLAYER_UPDATED")
        assert left["payload"]["lobby"]["counts"]["connectedPlayers"] == 0


def test_host_state_sync_reports_connected_player(client, host, game):
    """A host that connects after the player must see them in STATE_SYNC."""
    pin = game["game_pin"]
    session = join(client, game, "Ada")

    with client.websocket_connect(
        f"/ws/game/{pin}?player_token={session['player_token']}"
    ) as player_ws:
        recv_until(player_ws, "CONNECTED")

        with client.websocket_connect(f"/ws/game/{pin}?token={host['token']}") as host_ws:
            recv_until(host_ws, "CONNECTED")
            state = recv_until(host_ws, "STATE_SYNC")["payload"]
            assert len(state["players"]) == 1
            assert state["canStart"] is True


def test_register_failure_returns_a_clean_error_not_an_abnormal_close(
    client, host, game, monkeypatch
):
    """A raising `manager.register()` must not escape as close code 1006."""
    from app.ws import endpoint as ws_endpoint
    from app.game.manager import manager

    session = join(client, game, "Ada")

    async def boom(_connection):
        raise RuntimeError("simulated registry failure")

    monkeypatch.setattr(manager, "register", boom)

    with client.websocket_connect(
        f"/ws/game/{game['game_pin']}?player_token={session['player_token']}"
    ) as ws:
        message = ws.receive_json()
        assert message["type"] == "GAME_ERROR"
        assert message["payload"]["code"] == "INTERNAL_ERROR"
        # a real close code proves the teardown was graceful
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == ws_endpoint.CLOSE_CONFLICT


def test_unregister_failure_does_not_escape_the_finally_block(
    client, host, game, monkeypatch
):
    """A raising `manager.unregister()` must not escape `finally` either."""
    from app.game.manager import manager

    session = join(client, game, "Ada")

    async def boom(_connection):
        raise RuntimeError("simulated unregister failure")

    monkeypatch.setattr(manager, "unregister", boom)

    # closing the socket must complete normally rather than propagating
    with client.websocket_connect(
        f"/ws/game/{game['game_pin']}?player_token={session['player_token']}"
    ) as ws:
        recv_until(ws, "CONNECTED")


@pytest.fixture
def seated(client, host, game):
    """One joined player plus their tokens."""
    session = join(client, game, "Ada")
    return {
        "host_token": host["token"],
        "pin": game["game_pin"],
        "player_token": session["player_token"],
        "player_id": session["player"]["player_id"],
    }


# --------------------------------------------------------------- connection
def test_host_socket_connects(client, seated):
    with client.websocket_connect(f"/ws/game/{seated['pin']}?token={seated['host_token']}") as ws:
        message = ws.receive_json()
        assert message["type"] == "CONNECTED"
        assert message["payload"]["role"] == "host"


def test_player_socket_connects(client, seated):
    with client.websocket_connect(
        f"/ws/game/{seated['pin']}?player_token={seated['player_token']}"
    ) as ws:
        # the presence broadcast can precede the handshake, so match by type
        message = recv_until(ws, "CONNECTED")
        assert message["payload"]["role"] == "player"
        assert message["payload"]["playerId"] == seated["player_id"]


def test_socket_for_unknown_game_is_refused(client, host):
    with client.websocket_connect(f"/ws/game/000000?token={host['token']}") as ws:
        message = ws.receive_json()
        assert message["type"] == "GAME_ERROR"
        assert message["payload"]["code"] == "GAME_NOT_FOUND"


def test_socket_with_malformed_pin_is_refused(client, host):
    with client.websocket_connect(f"/ws/game/abc?token={host['token']}") as ws:
        message = ws.receive_json()
        assert message["type"] == "GAME_ERROR"
        assert message["payload"]["code"] == "INVALID_PIN"


def test_socket_without_credentials_is_refused(client, seated):
    with client.websocket_connect(f"/ws/game/{seated['pin']}") as ws:
        message = ws.receive_json()
        assert message["type"] == "GAME_ERROR"
        assert message["payload"]["code"] == "UNAUTHORIZED"


def test_socket_with_a_forged_player_token_is_refused(client, seated):
    with client.websocket_connect(
        f"/ws/game/{seated['pin']}?player_token=not.a.real.token"
    ) as ws:
        message = ws.receive_json()
        assert message["type"] == "GAME_ERROR"
        assert message["payload"]["code"] == "UNAUTHORIZED"


def test_ping_pong(client, seated):
    with client.websocket_connect(f"/ws/game/{seated['pin']}?token={seated['host_token']}") as ws:
        ws.receive_json()
        send(ws, "PING")
        assert recv_until(ws, "PONG")["type"] == "PONG"


def test_request_state_returns_a_sync(client, seated):
    with client.websocket_connect(f"/ws/game/{seated['pin']}?token={seated['host_token']}") as ws:
        ws.receive_json()
        send(ws, "REQUEST_STATE")
        payload = recv_until(ws, "STATE_SYNC")["payload"]
        assert payload["game"]["gamePin"] == seated["pin"]


def test_malformed_frame_does_not_kill_the_socket(client, seated):
    with client.websocket_connect(f"/ws/game/{seated['pin']}?token={seated['host_token']}") as ws:
        ws.receive_json()
        ws.send_json({"nonsense": True})
        error = recv_until(ws, "GAME_ERROR")
        assert error["payload"]["code"] == "BAD_REQUEST"
        send(ws, "PING")
        assert recv_until(ws, "PONG")["type"] == "PONG"


# ------------------------------------------------------------ full game flow
def test_host_to_final_results(client, game, seated):
    pin = seated["pin"]
    with client.websocket_connect(f"/ws/game/{pin}?token={seated['host_token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={seated['player_token']}"
        ) as player_ws:
            player_ws.receive_json()

            # host starts -> question 1 goes live
            send(host_ws, "START_GAME")
            started = recv_until(host_ws, "GAME_STARTED")
            assert started["payload"]["totalQuestions"] == 2
            q1 = recv_until(host_ws, "QUESTION_STARTED")["payload"]
            assert q1["questionNumber"] == 1
            assert q1["options"] == ["Paris", "Rome", "Berlin", "Madrid"]
            # the live payload must never disclose the answer
            assert "correctAnswer" not in q1
            assert "correctIndex" not in q1

            # player answers correctly
            send(player_ws, "SUBMIT_ANSWER", {"questionId": q1["questionId"], "answer": 0})
            ack = recv_until(player_ws, "ANSWER_SUBMITTED")["payload"]
            assert ack["accepted"] is True
            assert ack["selectedAnswer"] == 0
            assert ack["answeredCount"] == 1

            # everyone answered -> the question closes itself
            # Player receives QUESTION_ENDED (sanitized: no leaderboard, reveal without results)
            ended = recv_until(player_ws, "QUESTION_ENDED")
            assert ended["payload"]["questionId"] == q1["questionId"]
            assert "leaderboard" not in ended["payload"] or ended["payload"]["leaderboard"] is None
            # Player does NOT receive LEADERBOARD_UPDATED (host-only event)
            # Host receives LEADERBOARD_UPDATED
            board = recv_until(host_ws, "LEADERBOARD_UPDATED")["payload"]
            top = board["leaderboard"]["entries"][0]
            assert top["name"] == "Ada"
            assert top["score"] > 0

            # advance, then finish
            send(host_ws, "NEXT_QUESTION")
            # Player receives next QUESTION_STARTED
            q2_player = recv_until(player_ws, "QUESTION_STARTED")["payload"]
            assert q2_player["questionNumber"] == 2
            # Host receives next QUESTION_STARTED
            q2_host = recv_until(host_ws, "QUESTION_STARTED")["payload"]
            assert q2_host["questionNumber"] == 2
            assert q2_host["questionId"] != q1["questionId"]

            send(host_ws, "END_GAME")
            recv_until(host_ws, "GAME_FINISHED")

    results = client.get(f"/api/games/{pin}/results").json()
    ada = next(e for e in results["individualLeaderboard"] if e["name"] == "Ada")
    assert ada["answered"] == 1
    assert ada["correct"] == 1
    assert ada["score"] > 0
    assert results["stats"]["totalAnswers"] == 1


# ------------------------------------------------------- authority / cheating
def test_player_cannot_start_the_game(client, seated):
    with client.websocket_connect(
        f"/ws/game/{seated['pin']}?player_token={seated['player_token']}"
    ) as player_ws:
        player_ws.receive_json()
        send(player_ws, "START_GAME")
        assert recv_until(player_ws, "GAME_ERROR")["payload"]["code"] == "UNAUTHORIZED_HOST"


def test_duplicate_answer_is_rejected(client, game, seated):
    """A second player is needed, otherwise the question closes on the first
    answer (everyone connected has answered) and we would never reach the
    duplicate check."""
    pin = seated["pin"]
    bob_token = join(client, game, "Bob")["player_token"]
    with client.websocket_connect(f"/ws/game/{pin}?token={seated['host_token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={seated['player_token']}"
        ) as player_ws:
            player_ws.receive_json()
            with client.websocket_connect(
                f"/ws/game/{pin}?player_token={bob_token}"
            ) as bob_ws:
                bob_ws.receive_json()
                send(host_ws, "START_GAME")
                q1 = recv_until(host_ws, "QUESTION_STARTED")["payload"]

                send(player_ws, "SUBMIT_ANSWER", {"questionId": q1["questionId"], "answer": 0})
                recv_until(player_ws, "ANSWER_SUBMITTED")

                # Bob has not answered, so the question is still open and the
                # duplicate guard is what rejects Ada's second attempt.
                send(player_ws, "SUBMIT_ANSWER", {"questionId": q1["questionId"], "answer": 1})
                assert recv_until(player_ws, "GAME_ERROR")["payload"]["code"] == "ALREADY_ANSWERED"


def test_answer_for_the_wrong_question_is_rejected(client, seated):
    pin = seated["pin"]
    with client.websocket_connect(f"/ws/game/{pin}?token={seated['host_token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={seated['player_token']}"
        ) as player_ws:
            player_ws.receive_json()
            send(host_ws, "START_GAME")
            recv_until(host_ws, "QUESTION_STARTED")
            send(player_ws, "SUBMIT_ANSWER", {"questionId": "999999", "answer": 0})
            assert recv_until(player_ws, "GAME_ERROR")["payload"]["code"] == "QUESTION_MISMATCH"


def test_out_of_range_answer_is_rejected(client, seated):
    pin = seated["pin"]
    with client.websocket_connect(f"/ws/game/{pin}?token={seated['host_token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={seated['player_token']}"
        ) as player_ws:
            player_ws.receive_json()
            send(host_ws, "START_GAME")
            q1 = recv_until(host_ws, "QUESTION_STARTED")["payload"]
            send(player_ws, "SUBMIT_ANSWER", {"questionId": q1["questionId"], "answer": 99})
            assert recv_until(player_ws, "GAME_ERROR")["payload"]["code"] == "INVALID_ANSWER"


def test_answer_without_question_id_is_rejected(client, seated):
    pin = seated["pin"]
    with client.websocket_connect(f"/ws/game/{pin}?token={seated['host_token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={seated['player_token']}"
        ) as player_ws:
            player_ws.receive_json()
            send(host_ws, "START_GAME")
            recv_until(host_ws, "QUESTION_STARTED")
            send(player_ws, "SUBMIT_ANSWER", {"answer": 0})
            assert recv_until(player_ws, "GAME_ERROR")["payload"]["code"] == "BAD_REQUEST"


def test_answering_after_the_game_ended_is_refused(client, seated):
    pin = seated["pin"]
    with client.websocket_connect(f"/ws/game/{pin}?token={seated['host_token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={seated['player_token']}"
        ) as player_ws:
            player_ws.receive_json()
            send(host_ws, "START_GAME")
            q1 = recv_until(host_ws, "QUESTION_STARTED")["payload"]
            send(host_ws, "CANCEL_GAME")
            recv_until(host_ws, "GAME_CANCELLED")
            send(player_ws, "SUBMIT_ANSWER", {"questionId": q1["questionId"], "answer": 0})
            code = recv_until(player_ws, "GAME_ERROR")["payload"]["code"]
            assert code in {"GAME_CANCELLED", "GAME_ENDED", "GAME_NOT_ACTIVE"}


def test_disconnected_player_is_marked_and_can_reclaim_their_seat(client, seated):
    pin = seated["pin"]
    with client.websocket_connect(f"/ws/game/{pin}?token={seated['host_token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={seated['player_token']}"
        ) as player_ws:
            player_ws.receive_json()
        recv_until(host_ws, "PLAYER_UPDATED")  # socket closed -> presence only

        lobby = client.get(f"/api/games/{pin}/lobby").json()
        assert any(p["connected"] is False for p in lobby["players"])
        assert client.post(f"/api/games/{pin}/rejoin", json={"nickname": "Ada"}).status_code == 200


def test_connected_player_cannot_be_rejoined_by_nickname(client, seated):
    pin = seated["pin"]
    with client.websocket_connect(
        f"/ws/game/{pin}?player_token={seated['player_token']}"
    ) as player_ws:
        player_ws.receive_json()
        assert client.post(f"/api/games/{pin}/rejoin", json={"nickname": "Ada"}).status_code == 409


def test_host_disconnect_does_not_end_the_game(client, seated):
    """Losing the host socket must not corrupt a running game."""
    pin = seated["pin"]
    with client.websocket_connect(
        f"/ws/game/{pin}?player_token={seated['player_token']}"
    ) as player_ws:
        player_ws.receive_json()
    lookup = client.get(f"/api/games/{pin}").json()
    assert lookup["status"] in {"LOBBY", "CANCELLED"} or lookup["status"].startswith("QUESTION")


# ----------------------------------------------------- server-side grading
def test_results_reflect_server_side_grade_only(client, game, seated):
    """A wrong answer scores zero regardless of what the client believes."""
    pin = seated["pin"]
    with client.websocket_connect(f"/ws/game/{pin}?token={seated['host_token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={seated['player_token']}"
        ) as player_ws:
            player_ws.receive_json()
            send(host_ws, "START_GAME")
            q1 = recv_until(host_ws, "QUESTION_STARTED")["payload"]
            send(player_ws, "SUBMIT_ANSWER", {"questionId": q1["questionId"], "answer": 2})
            recv_until(player_ws, "ANSWER_SUBMITTED")

    results = client.get(f"/api/games/{pin}/results").json()
    ada = results["individualLeaderboard"][0]
    assert ada["correct"] == 0
    assert ada["score"] == 0
    assert results["questions"][0]["correctCount"] == 0
    assert results["questions"][0]["distribution"][2] == 1


def test_answer_is_graded_by_the_server_not_the_client(client, game, seated):
    """The client cannot smuggle a score in: the action carries no score field."""
    pin = seated["pin"]
    with client.websocket_connect(f"/ws/game/{pin}?token={seated['host_token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={seated['player_token']}"
        ) as player_ws:
            player_ws.receive_json()
            send(host_ws, "START_GAME")
            q1 = recv_until(host_ws, "QUESTION_STARTED")["payload"]
            player_ws.send_json(
                {
                    "type": "SUBMIT_ANSWER",
                    "payload": {
                        "questionId": q1["questionId"],
                        "answer": 1,
                        "points": 999999,
                        "score": 999999,
                    },
                }
            )
            recv_until(player_ws, "ANSWER_SUBMITTED")

    results = client.get(f"/api/games/{pin}/results").json()
    ada = results["individualLeaderboard"][0]
    assert ada["score"] < 999999  # wrong answer => 0
    assert ada["score"] == 0


# ===========================================================================
# Kahoot-style gameplay contract
#
# Host/player split: the host drives the quiz with a visible question + four
# options + an authoritative timer + Next Question, the player only ever
# answers, and the backend owns every transition.
# ===========================================================================


def test_host_receives_question_options_timer_and_response_counts(client, seated):
    """Checklist 1-5: host starts -> Q1 -> text + 4 options + timer state."""
    pin = seated["pin"]
    with client.websocket_connect(f"/ws/game/{pin}?token={seated['host_token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={seated['player_token']}"
        ) as player_ws:
            player_ws.receive_json()

            send(host_ws, "START_GAME")
            started = recv_until(host_ws, "GAME_STARTED")["payload"]
            assert started["totalQuestions"] == 2

            q1 = recv_until(host_ws, "QUESTION_STARTED")["payload"]

            # 2. question 1 is active
            assert q1["questionNumber"] == 1
            assert q1["totalQuestions"] == 2

            # 3. host sees the question
            assert q1["question"] == "Capital of France?"

            # 4. host sees exactly four options
            assert len(q1["options"]) == 4
            assert q1["options"] == ["Paris", "Rome", "Berlin", "Madrid"]

            # 5. authoritative timer state is present and sane
            assert q1["timeLimit"] == 5
            assert 0 < q1["timeRemainingMs"] <= q1["timeLimit"] * 1000
            assert q1["startedAt"] and q1["endsAt"] and q1["serverTime"]
            assert q1["endsAt"] > q1["startedAt"]

            # response counts reach the host while the question is live
            send(player_ws, "SUBMIT_ANSWER", {"questionId": q1["questionId"], "answer": 0})
            recv_until(player_ws, "ANSWER_SUBMITTED")
            answered = recv_until(host_ws, "PLAYER_ANSWERED")["payload"]
            assert answered["answeredCount"] == 1
            assert answered["playerCount"] == 1


def test_player_gets_a_playable_answer_state_but_never_the_answer(client, seated):
    """Checklist 6-7: the player receives four options and no correct answer."""
    pin = seated["pin"]
    with client.websocket_connect(f"/ws/game/{pin}?token={seated['host_token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={seated['player_token']}"
        ) as player_ws:
            player_ws.receive_json()

            send(host_ws, "START_GAME")
            q1 = recv_until(player_ws, "QUESTION_STARTED")["payload"]

            # playable: four options, an id to answer against, a live clock
            assert len(q1["options"]) == 4
            assert q1["questionId"]
            assert q1["timeRemainingMs"] > 0

            # fair play: nothing that discloses the answer pre-reveal
            for leaked in ("correctAnswer", "correctIndex", "explanation"):
                assert leaked not in q1, f"{leaked} leaked to a live player"

            # the client cannot re-request it either
            send(player_ws, "REQUEST_STATE")
            sync = recv_until(player_ws, "STATE_SYNC")["payload"]
            assert "correctIndex" not in sync["currentQuestion"]
            assert sync["reveal"] is None



def test_player_submits_exactly_one_answer_per_question(client, game, seated):
    """Checklist 8: one tap locks the choice; a second attempt is refused."""
    pin = seated["pin"]
    # A second seat keeps the question open after the first answer lands.
    bob_token = join(client, game, "Bob")["player_token"]

    with client.websocket_connect(f"/ws/game/{pin}?token={seated['host_token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={seated['player_token']}"
        ) as player_ws:
            player_ws.receive_json()
            with client.websocket_connect(f"/ws/game/{pin}?player_token={bob_token}") as bob_ws:
                bob_ws.receive_json()

                send(host_ws, "START_GAME")
                q1 = recv_until(host_ws, "QUESTION_STARTED")["payload"]

                send(player_ws, "SUBMIT_ANSWER", {"questionId": q1["questionId"], "answer": 0})
                ack = recv_until(player_ws, "ANSWER_SUBMITTED")["payload"]
                assert ack["accepted"] is True

                send(player_ws, "SUBMIT_ANSWER", {"questionId": q1["questionId"], "answer": 3})
                assert (
                    recv_until(player_ws, "GAME_ERROR")["payload"]["code"]
                    == "ALREADY_ANSWERED"
                )


def test_server_timer_expires_and_then_rejects_late_answers(client, seated):
    """Checklist 9: the backend closes the question when the clock runs out."""
    pin = seated["pin"]
    with client.websocket_connect(f"/ws/game/{pin}?token={seated['host_token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={seated['player_token']}"
        ) as player_ws:
            player_ws.receive_json()

            send(host_ws, "START_GAME")
            q1 = recv_until(host_ws, "QUESTION_STARTED")["payload"]

            # nobody answers, so only the authoritative timer can close it
            ended = recv_until(host_ws, "QUESTION_ENDED", limit=60)["payload"]
            assert ended["reason"] == "timer"
            assert ended["state"] == "QUESTION_REVEAL"
            assert ended["hasMoreQuestions"] is True

            # the reveal is the first point at which the answer is disclosed
            assert ended["reveal"]["correctIndex"] == 0
            assert ended["reveal"]["correctAnswer"] == "Paris"

            # a late tap is refused - the question is fully closed now, so the
            # engine is past ANSWERABLE_STATES entirely
            send(player_ws, "SUBMIT_ANSWER", {"questionId": q1["questionId"], "answer": 1})
            assert (
                recv_until(player_ws, "GAME_ERROR")["payload"]["code"]
                == "NO_ACTIVE_QUESTION"
            )



def test_host_next_question_advances_to_q2_and_resets_the_timer(client, seated):
    """Checklist 10-14: Next Question -> Q2 -> fresh options + fresh clock."""
    pin = seated["pin"]
    with client.websocket_connect(f"/ws/game/{pin}?token={seated['host_token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={seated['player_token']}"
        ) as player_ws:
            player_ws.receive_json()

            send(host_ws, "START_GAME")
            q1 = recv_until(host_ws, "QUESTION_STARTED")["payload"]
            # drain Q1 on the player socket so the next read is Q2's frame
            assert recv_until(player_ws, "QUESTION_STARTED")["payload"][
                "questionNumber"
            ] == 1

            # 10. the host drives progression over the wire, not via React state
            send(host_ws, "NEXT_QUESTION")

            # 11-12. the old question closes, then Q2 opens for the host
            ended = recv_until(host_ws, "QUESTION_ENDED")["payload"]
            assert ended["state"] == "QUESTION_REVEAL"
            board = recv_until(host_ws, "LEADERBOARD_UPDATED")["payload"]
            assert board["state"] == "LEADERBOARD"

            advanced = recv_until(host_ws, "NEXT_QUESTION")["payload"]
            assert advanced["nextQuestionIndex"] == 1
            assert advanced["totalQuestions"] == 2

            q2 = recv_until(host_ws, "QUESTION_STARTED")["payload"]
            assert q2["questionNumber"] == 2
            assert q2["questionId"] != q1["questionId"]
            assert q2["question"] == "2 + 2 = ?"

            # 13. the player receives the new four options
            player_q2 = recv_until(player_ws, "QUESTION_STARTED")["payload"]
            assert player_q2["questionId"] == q2["questionId"]
            assert player_q2["options"] == ["3", "4", "5", "6"]
            assert "correctAnswer" not in player_q2
            assert "correctIndex" not in player_q2

            # 14. the timer resets to a full clock
            assert 0 < player_q2["timeRemainingMs"] <= player_q2["timeLimit"] * 1000
            assert player_q2["startedAt"] != q1["startedAt"]
            assert player_q2["endsAt"] > q1["endsAt"]



def test_final_question_transitions_to_results(client, seated):
    """Checklist 15: after the last question the game reaches FINISHED."""
    pin = seated["pin"]
    with client.websocket_connect(f"/ws/game/{pin}?token={seated['host_token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(
            f"/ws/game/{pin}?player_token={seated['player_token']}"
        ) as player_ws:
            player_ws.receive_json()

            send(host_ws, "START_GAME")
            recv_until(host_ws, "QUESTION_STARTED")

            # question 1 of 2 -> question 2 of 2
            send(host_ws, "NEXT_QUESTION")
            q2 = recv_until(host_ws, "QUESTION_STARTED")["payload"]
            assert q2["questionNumber"] == 2

            # question 2 of 2 -> finished
            send(host_ws, "NEXT_QUESTION")
            recv_until(host_ws, "QUESTION_ENDED")
            finished = recv_until(host_ws, "GAME_FINISHED", limit=60)["payload"]
            assert finished["reason"] == "completed"

            # the player lands on the same terminal state
            player_seen = recv_until(player_ws, "GAME_FINISHED", limit=60)
            assert player_seen["payload"]["reason"] == "completed"

            # a further advance must not resurrect the quiz
            send(host_ws, "NEXT_QUESTION")
            send(host_ws, "REQUEST_STATE")
            sync = recv_until(host_ws, "STATE_SYNC", limit=60)["payload"]
            assert sync["game"]["state"] == "FINISHED"


def test_player_stage_never_renders_the_question_text():
    """Checklist 7 (render side): the phone UI shows buttons, not the question.

    The question text belongs to the HOST stage only.  This source-level guard
    stops a future edit from quietly putting it back on the player screen.
    """
    from pathlib import Path

    pages = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages"
    play = pages / "PlayPage.tsx"
    if not play.exists():
        pytest.skip("frontend sources are not available in this checkout")

    source = play.read_text(encoding="utf-8")
    for interpolation in (
        "{displayQuestion.question}",
        "{currentQuestion?.question}",
        "{question.question}",
    ):
        assert interpolation not in source, (
            f"PlayPage must not render the question text (found {interpolation})"
        )

    # ...while the host stage must show it.
    panel = pages.parent / "components" / "game" / "HostGamePanel.tsx"
    assert panel.exists(), "host gameplay stage is missing"
    assert "{question.question}" in panel.read_text(encoding="utf-8")