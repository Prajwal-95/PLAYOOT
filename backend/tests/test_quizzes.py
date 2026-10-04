"""Quiz CRUD, ownership and authorisation."""

from __future__ import annotations

from conftest import question


def test_create_quiz_with_questions(client, host):
    response = client.post(
        "/api/quizzes",
        headers=host["headers"],
        json={
            "title": "Capitals",
            "description": "geo",
            "source_type": "manual",
            "questions": [
                question("Capital of Spain?", ["Madrid", "Lisbon", "Rome"], "Madrid"),
            ],
        },
    )
    assert response.status_code in (200, 201)
    body = response.json()
    assert body["title"] == "Capitals"
    assert body["question_count"] == 1
    assert len(body["questions"]) == 1
    assert body["questions"][0]["options"] == ["Madrid", "Lisbon", "Rome"]


def test_create_quiz_rejects_duplicate_options(client, host):
    response = client.post(
        "/api/quizzes",
        headers=host["headers"],
        json={
            "title": "Bad",
            "source_type": "manual",
            "questions": [
                question("Pick one", ["same", "same", "other"], "same"),
            ],
        },
    )
    assert response.status_code == 422


def test_create_quiz_rejects_correct_answer_not_in_options(client, host):
    response = client.post(
        "/api/quizzes",
        headers=host["headers"],
        json={
            "title": "Bad",
            "source_type": "manual",
            "questions": [
                question("Pick one", ["a", "b"], "zzz"),
            ],
        },
    )
    assert response.status_code == 422


def test_create_quiz_rejects_true_false_without_options(client, host):
    response = client.post(
        "/api/quizzes",
        headers=host["headers"],
        json={
            "title": "Bad TF",
            "source_type": "manual",
            "questions": [
                {
                    "question_text": "Sky is blue",
                    "question_type": "true_false",
                    "options": [],
                    "correct_answer": "True",
                    "time_limit": 10,
                    "points": 100,
                }
            ],
        },
    )
    assert response.status_code == 422


def test_list_quizzes_only_returns_own(client, host, other_host, quiz):
    mine = client.get("/api/quizzes", headers=host["headers"])
    assert mine.status_code == 200
    assert any(q["title"] == "Smoke Quiz" for q in mine.json())

    theirs = client.get("/api/quizzes", headers=other_host["headers"])
    assert theirs.status_code == 200
    assert all(q["title"] != "Smoke Quiz" for q in theirs.json())


def test_get_quiz(client, host, quiz):
    response = client.get(f"/api/quizzes/{quiz['id']}", headers=host["headers"])
    assert response.status_code == 200
    assert response.json()["id"] == quiz["id"]


def test_get_other_users_quiz_is_forbidden(client, other_host, quiz):
    response = client.get(f"/api/quizzes/{quiz['id']}", headers=other_host["headers"])
    assert response.status_code in (403, 404)


def test_update_quiz(client, host, quiz):
    response = client.put(
        f"/api/quizzes/{quiz['id']}",
        headers=host["headers"],
        json={
            "title": "Renamed",
            "description": "updated",
            "questions": [
                question("Capital of Italy?", ["Rome", "Milan", "Turin"], "Rome"),
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Renamed"
    assert body["question_count"] == 1


def test_update_other_users_quiz_is_forbidden(client, other_host, quiz):
    response = client.put(
        f"/api/quizzes/{quiz['id']}",
        headers=other_host["headers"],
        json={"title": "Hijacked", "questions": []},
    )
    assert response.status_code in (403, 404)


def test_delete_quiz(client, host, quiz):
    assert client.delete(
        f"/api/quizzes/{quiz['id']}", headers=host["headers"]
    ).status_code == 204
    remaining = client.get("/api/quizzes", headers=host["headers"]).json()
    assert all(q["id"] != quiz["id"] for q in remaining)


def test_delete_other_users_quiz_is_forbidden(client, other_host, quiz):
    response = client.delete(f"/api/quizzes/{quiz['id']}", headers=other_host["headers"])
    assert response.status_code in (403, 404)
    # still there
    assert client.get(
        f"/api/quizzes/{quiz['id']}", headers=other_host["headers"]
    ).status_code in (403, 404)