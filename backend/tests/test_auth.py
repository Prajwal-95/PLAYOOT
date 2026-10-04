"""Auth: registration, login, invalid credentials, /me, authorisation."""

from __future__ import annotations

from uuid import uuid4

from conftest import VALID_PASSWORD


def test_health_endpoint(client):
    """Liveness must stay free of infrastructure detail."""
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    # deliberately absent from the public surface
    for forbidden in ("database", "socketRooms", "activeGames", "aiConfigured"):
        assert forbidden not in body


def test_health_never_leaks_secrets_or_game_pins(client, game):
    body = client.get("/api/health").text
    for banned in ("gsk_", "BEGIN PRIVATE KEY", "postgresql://", "sqlite:///", "password"):
        assert banned not in body


def test_readiness_endpoint_checks_the_database(client):
    response = client.get("/api/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["databaseReachable"] is True
    assert body["database"] in {"sqlite", "postgresql"}
    assert "sqlite:///" not in response.text
    assert "postgresql://" not in response.text


def test_readiness_does_not_list_live_game_pins(client, game):
    body = client.get("/api/ready").json()
    assert "socketRooms" not in body
    assert game["game_pin"] not in client.get("/api/ready").text


def test_root_advertises_health_and_readiness(client):
    body = client.get("/").json()
    assert body["health"] == "/api/health"
    assert body["readiness"] == "/api/ready"


def test_root_advertises_endpoints(client):
    body = client.get("/").json()
    assert body["rest"] == "/api"
    assert body["websocket"].startswith("/ws/game/")


def test_register_returns_token_and_user(client):
    email = f"reg_{uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/auth/register",
        json={"name": "Ada", "email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == email
    assert body["user"]["auth_provider"] == "email"
    # the password hash must never come back
    assert "password" not in response.text.lower()


def test_register_normalises_email(client):
    email = f"MiXeD_{uuid4().hex[:6]}@Example.COM"
    response = client.post(
        "/api/auth/register",
        json={"name": "Bo", "email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    assert response.json()["user"]["email"] == email.lower()


def test_register_duplicate_email_conflicts(client, host):
    response = client.post(
        "/api/auth/register",
        json={"name": "Copy", "email": host["email"], "password": VALID_PASSWORD},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EMAIL_TAKEN"


def test_register_rejects_short_password(client):
    response = client.post(
        "/api/auth/register",
        json={"name": "Short", "email": f"s_{uuid4().hex[:8]}@example.com", "password": "abc"},
    )
    assert response.status_code == 422


def test_register_rejects_bad_email(client):
    response = client.post(
        "/api/auth/register",
        json={"name": "Bad", "email": "not-an-email", "password": VALID_PASSWORD},
    )
    assert response.status_code == 422


def test_login_succeeds_with_correct_password(client, host):
    response = client.post(
        "/api/auth/login", json={"email": host["email"], "password": host["password"]}
    )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == host["email"]


def test_login_with_wrong_password_is_401(client, host):
    response = client.post(
        "/api/auth/login", json={"email": host["email"], "password": "TotallyWrong123"}
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INVALID_CREDENTIALS"


def test_login_unknown_email_is_401(client):
    response = client.post(
        "/api/auth/login",
        json={"email": f"ghost_{uuid4().hex[:8]}@example.com", "password": VALID_PASSWORD},
    )
    assert response.status_code == 401


def test_login_does_not_reveal_whether_email_exists(client, host):
    """Credential stuffing defence: identical error for bad user and bad pass."""
    bad_pass = client.post(
        "/api/auth/login", json={"email": host["email"], "password": "WrongWrong123"}
    )
    bad_user = client.post(
        "/api/auth/login",
        json={"email": f"ghost_{uuid4().hex[:8]}@example.com", "password": "WrongWrong123"},
    )
    assert bad_pass.status_code == bad_user.status_code == 401
    assert bad_pass.json() == bad_user.json()


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_rejects_garbage_token(client):
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_me_returns_current_user(client, host):
    response = client.get("/api/auth/me", headers=host["headers"])
    assert response.status_code == 200
    assert response.json()["id"] == host["user"]["id"]


def test_quiz_endpoints_require_auth(client, quiz):
    assert client.get("/api/quizzes").status_code == 401
    assert client.get(f"/api/quizzes/{quiz['id']}").status_code == 401
    assert client.post("/api/games", json={"quiz_id": quiz["id"]}).status_code == 401