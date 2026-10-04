"""Game lifecycle over REST: create, lookup, join, rejoin, teams, results."""

from __future__ import annotations

import pytest

from conftest import join


# ------------------------------------------------------------------- creation
def test_create_game_requires_auth(client, quiz):
    assert client.post("/api/games", json={"quiz_id": quiz["id"]}).status_code == 401


def test_create_game_returns_numeric_pin(client, host, quiz):
    response = client.post(
        "/api/games",
        headers=host["headers"],
        json={"quiz_id": quiz["id"], "mode": "individual"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["game_pin"].isdigit()
    assert 6 <= len(body["game_pin"]) <= 8
    assert body["status"] == "LOBBY"
    assert body["question_count"] == 2
    assert body["joinable"] is True


def test_create_game_rejects_unknown_quiz(client, host):
    response = client.post("/api/games", headers=host["headers"], json={"quiz_id": 9_999_999})
    assert response.status_code in (403, 404)


def test_create_game_rejects_other_users_quiz(client, other_host, quiz):
    response = client.post(
        "/api/games", headers=other_host["headers"], json={"quiz_id": quiz["id"]}
    )
    assert response.status_code in (403, 404)


def test_create_game_rejects_invalid_mode(client, host, quiz):
    response = client.post(
        "/api/games", headers=host["headers"], json={"quiz_id": quiz["id"], "mode": "chaos"}
    )
    assert response.status_code == 422


# -------------------------------------------------------------------- lookup
def test_lookup_game_by_pin(client, game):
    response = client.get(f"/api/games/{game['game_pin']}")
    assert response.status_code == 200
    assert response.json()["game_pin"] == game["game_pin"]


def test_lookup_malformed_pin_is_400(client):
    response = client.get("/api/games/not-a-pin")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_PIN"


def test_lookup_unknown_pin_is_404(client):
    response = client.get("/api/games/000000")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "GAME_NOT_FOUND"


def test_lobby_snapshot(client, game):
    response = client.get(f"/api/games/{game['game_pin']}/lobby")
    assert response.status_code == 200
    assert response.json()["players"] == []


# ---------------------------------------------------------------------- join
def test_join_game_creates_player_and_token(client, game):
    body = join(client, game, "Ada")
    assert body["player"]["nickname"] == "Ada"
    assert body["player"]["score"] == 0
    assert body["player_token"]
    assert body["game"]["player_count"] == 1


def test_join_requires_nickname(client, game):
    response = client.post(f"/api/games/{game['game_pin']}/join", json={"nickname": ""})
    assert response.status_code == 422


def test_join_rejects_illegal_characters(client, game):
    response = client.post(
        f"/api/games/{game['game_pin']}/join", json={"nickname": "bad<script>"}
    )
    assert response.status_code == 422


def test_duplicate_nickname_conflicts(client, game):
    join(client, game, "Ada")
    response = client.post(f"/api/games/{game['game_pin']}/join", json={"nickname": "Ada"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "NICKNAME_TAKEN"


def test_join_unknown_game_is_404(client):
    assert client.post("/api/games/000000/join", json={"nickname": "Ada"}).status_code == 404


def test_rejoin_unknown_nickname_is_404(client, game):
    """Rejoin identifies the seat by nickname - there is no such player yet."""
    response = client.post(f"/api/games/{game['game_pin']}/rejoin", json={"nickname": "Nobody"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PLAYER_NOT_IN_GAME"


def test_rejoin_issues_a_new_token_for_an_unconnected_seat(client, game):
    """`connected` tracks the WebSocket, not the REST reservation.

    A player who joined but has not attached yet (or whose socket dropped) may
    reclaim their seat by nickname and get a fresh player token.
    """
    first = join(client, game, "Ada")
    response = client.post(f"/api/games/{game['game_pin']}/rejoin", json={"nickname": "Ada"})
    assert response.status_code == 200
    body = response.json()
    assert body["player"]["player_id"] == first["player"]["player_id"]
    assert body["player_token"]
    # still exactly one seat, nobody was duplicated
    lobby = client.get(f"/api/games/{game['game_pin']}/lobby").json()
    assert len(lobby["players"]) == 1


def test_leave_in_lobby_frees_the_seat(client, game):
    """Leaving before play starts removes the player outright."""
    token = join(client, game, "Ada")["player_token"]
    pin = game["game_pin"]
    assert client.post(
        f"/api/games/{pin}/leave", headers={"X-Player-Token": token}
    ).status_code == 204
    lobby = client.get(f"/api/games/{pin}/lobby").json()
    assert lobby["players"] == []
    # the nickname is free again
    assert client.post(f"/api/games/{pin}/join", json={"nickname": "Ada"}).status_code == 201


def test_leave_requires_token(client, game):
    assert client.post(f"/api/games/{game['game_pin']}/leave").status_code == 401


def test_leave_with_bogus_token_is_401(client, game):
    response = client.post(
        f"/api/games/{game['game_pin']}/leave", headers={"X-Player-Token": "garbage"}
    )
    assert response.status_code == 401


# --------------------------------------------------------------------- teams
@pytest.fixture
def team_game(client, host, quiz):
    response = client.post(
        "/api/games", headers=host["headers"], json={"quiz_id": quiz["id"], "mode": "team"}
    )
    assert response.status_code == 201
    return response.json()


def test_team_requires_team_mode(client, game):
    session = join(client, game, "Solo")
    response = client.post(
        f"/api/games/{game['game_pin']}/teams",
        json={"name": "Reds"},
        headers={"X-Player-Token": session["player_token"]},
    )
    assert response.status_code in (400, 409)


def test_create_and_join_team(client, team_game):
    pin = team_game["game_pin"]
    ada = join(client, team_game, "Ada")
    bob = join(client, team_game, "Bob")

    created = client.post(
        f"/api/games/{pin}/teams",
        json={"name": "Reds", "join": True},
        headers={"X-Player-Token": ada["player_token"]},
    )
    assert created.status_code == 201
    team = created.json()
    assert team["name"] == "Reds"

    joined = client.post(
        f"/api/games/{pin}/teams/join",
        json={"team_id": team["team_id"]},
        headers={"X-Player-Token": bob["player_token"]},
    )
    assert joined.status_code == 200

    listed = client.get(f"/api/games/{pin}/teams")
    assert listed.status_code == 200
    reds = next(t for t in listed.json() if t["name"] == "Reds")
    assert reds["member_count"] == 2


def test_duplicate_team_name_conflicts(client, team_game):
    pin = team_game["game_pin"]
    ada = join(client, team_game, "Ada")
    bob = join(client, team_game, "Bob")
    client.post(
        f"/api/games/{pin}/teams",
        json={"name": "Reds", "join": True},
        headers={"X-Player-Token": ada["player_token"]},
    )
    response = client.post(
        f"/api/games/{pin}/teams",
        json={"name": "Reds"},
        headers={"X-Player-Token": bob["player_token"]},
    )
    assert response.status_code == 409


def test_cannot_create_team_for_someone_else(client, team_game):
    ada = join(client, team_game, "Ada")
    bob = join(client, team_game, "Bob")
    response = client.post(
        f"/api/games/{team_game['game_pin']}/teams",
        json={"name": "Reds", "player_id": bob["player"]["player_id"]},
        headers={"X-Player-Token": ada["player_token"]},
    )
    assert response.status_code in (401, 403)


def test_team_actions_require_player_token(client, team_game):
    pin = team_game["game_pin"]
    join(client, team_game, "Ada")
    assert client.post(f"/api/games/{pin}/teams", json={"name": "Reds"}).status_code == 401


# ------------------------------------------------------------------- results
def test_results_for_unknown_game_is_404(client):
    assert client.get("/api/games/000000/results").status_code == 404


def test_results_before_any_answers(client, game):
    join(client, game, "Ada")
    response = client.get(f"/api/games/{game['game_pin']}/results")
    assert response.status_code == 200
    body = response.json()
    assert body["game"]["gamePin"] == game["game_pin"]
    assert body["stats"]["totalAnswers"] == 0
    assert body["stats"]["accuracy"] == 0.0
    assert len(body["questions"]) == 2

    entry = body["individualLeaderboard"][0]
    assert entry["name"] == "Ada"
    assert entry["score"] == 0
    assert entry["answered"] == 0
    assert entry["accuracy"] == 0.0
    assert entry["rank"] == 1


def test_results_expose_per_question_stats(client, game):
    join(client, game, "Ada")
    body = client.get(f"/api/games/{game['game_pin']}/results").json()
    first = body["questions"][0]
    assert first["questionNumber"] == 1
    assert first["correctIndex"] == 0
    assert first["distribution"] == [0, 0, 0, 0]
    assert first["answeredCount"] == 0