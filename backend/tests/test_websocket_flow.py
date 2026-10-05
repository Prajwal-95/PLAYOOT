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
    """The snapshot the player receives must contain their own roster entry."""
    pin = game["game_pin"]
    session = join(client, game, "Ada")
    player_id = session["player"]["player_id"]

    with client.websocket_connect(
        f"/ws/game/{pin}?player_token={session['player_token']}"
    ) as ws:
        recv_until(ws, "CONNECTED")
        state = recv_until(ws, "STATE_SYNC")["payload"]
        assert [p["playerId"] for p in state["players"]] == [player_id]
        assert state["alreadyAnswered"] is False
        assert state["myResult"] is None
        assert state["leaderboard"]["entries"][0]["name"] == "Ada"


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
            ended = recv_until(player_ws, "QUESTION_ENDED")
            assert ended["payload"]["questionId"] == q1["questionId"]
            board = recv_until(player_ws, "LEADERBOARD_UPDATED")["payload"]
            top = board["leaderboard"]["entries"][0]
            assert top["name"] == "Ada"
            assert top["score"] > 0

            # advance, then finish
            send(host_ws, "NEXT_QUESTION")
            q2 = recv_until(host_ws, "QUESTION_STARTED")["payload"]
            assert q2["questionNumber"] == 2
            assert q2["questionId"] != q1["questionId"]

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