"""AI generation contract.

Groq is NEVER contacted here: ``get_quiz_generator`` is replaced with a fake, so
the suite costs zero credits and cannot flake because of the provider.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.ai.base import (
    GeneratedQuestion,
    GenerationRequest,
    QuizGenerationError,
    extract_json,
    normalise_questions,
)


class FakeGenerator:
    def __init__(self, questions=None, error: QuizGenerationError | None = None):
        self._questions = questions or []
        self._error = error
        self.requests: list[GenerationRequest] = []

    @property
    def provider(self) -> str:
        return "fake"

    async def generate(self, request: GenerationRequest):
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        # Mirror the real generator: per-question timing/points come from the
        # request, not from the canned question.
        return [
            replace(q, time_limit=request.time_limit, points=request.points)
            for q in self._questions
        ]


@pytest.fixture
def install_generator(monkeypatch):
    import app.api.routes_quiz as routes_quiz

    def _install(generator):
        monkeypatch.setattr(routes_quiz, "get_quiz_generator", lambda: generator)
        return generator

    return _install


def make_question(**overrides) -> GeneratedQuestion:
    data = dict(
        question_text="Capital of France?",
        question_type="multiple_choice",
        options=["Paris", "Rome", "Berlin", "Madrid"],
        correct_answer="Paris",
        correct_answers=[],
        explanation="Paris has been the capital since 987.",
        time_limit=20,
        points=1000,
    )
    data.update(overrides)
    return GeneratedQuestion(**data)


BASE_PAYLOAD = {
    "source_type": "topic",
    "topic": "World Capitals",
    "question_count": 2,
    "difficulty": "mixed",
    "option_count": 4,
    "save": False,
}


# ------------------------------------------------------------------ happy path
def test_generate_topic_returns_structured_questions(client, host, install_generator):
    install_generator(FakeGenerator([make_question(), make_question()]))
    response = client.post("/api/quizzes/generate", headers=host["headers"], json=BASE_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["generated_count"] == 2
    for item in body["questions"]:
        assert item["question_text"]
        assert item["question_type"] in (
            "multiple_choice",
            "multiple_answer",
            "fill_blank",
            "true_false",
        )
        assert len(item["options"]) >= 2
        assert item["correct_answer"] in item["options"]
        assert item["explanation"]
        assert item["time_limit"] == 20
        assert item["points"] == 1000


def test_generate_respects_count_and_difficulty(client, host, install_generator):
    generator = install_generator(FakeGenerator([make_question()]))
    payload = {**BASE_PAYLOAD, "question_count": 1, "difficulty": "hard", "time_limit": 30}
    response = client.post("/api/quizzes/generate", headers=host["headers"], json=payload)
    assert response.status_code == 200
    request = generator.requests[-1]
    assert request.question_count == 1
    assert request.difficulty == "hard"
    assert request.time_limit == 30
    assert response.json()["questions"][0]["time_limit"] == 30


def test_generate_prompt_source(client, host, install_generator):
    generator = install_generator(FakeGenerator([make_question()]))
    response = client.post(
        "/api/quizzes/generate",
        headers=host["headers"],
        json={
            "source_type": "prompt",
            "prompt": "React hooks",
            "question_count": 1,
            "save": False,
        },
    )
    assert response.status_code == 200
    assert generator.requests[-1].source_type == "prompt"


def test_generate_true_false_and_fill_blank_are_preserved(client, host, install_generator):
    install_generator(
        FakeGenerator(
            [
                make_question(
                    question_type="true_false",
                    options=["True", "False"],
                    correct_answer="True",
                ),
                make_question(question_type="fill_blank", options=[], correct_answer="Ottawa"),
            ]
        )
    )
    payload = {
        **BASE_PAYLOAD,
        "question_types": ["true_false", "fill_blank"],
        "option_count": 2,
    }
    response = client.post("/api/quizzes/generate", headers=host["headers"], json=payload)
    assert response.status_code == 200
    types = [q["question_type"] for q in response.json()["questions"]]
    assert types == ["true_false", "fill_blank"]


# ------------------------------------------------------------------ persistence
def test_generate_saves_quiz_when_requested(client, host, install_generator):
    install_generator(FakeGenerator([make_question(), make_question()]))
    response = client.post(
        "/api/quizzes/generate",
        headers=host["headers"],
        json={**BASE_PAYLOAD, "save": True, "winners_count": 5, "title": "AI Capitals"},
    )
    assert response.status_code == 200
    quiz = response.json()["quiz"]
    assert quiz is not None
    assert quiz["title"] == "AI Capitals"
    assert quiz["winners_count"] == 5

    stored = client.get(f"/api/quizzes/{quiz['id']}", headers=host["headers"])
    assert stored.status_code == 200
    assert stored.json()["question_count"] == 2


def test_generate_does_not_persist_when_save_false(client, host, install_generator):
    install_generator(FakeGenerator([make_question()]))
    before = len(client.get("/api/quizzes", headers=host["headers"]).json())
    response = client.post("/api/quizzes/generate", headers=host["headers"], json=BASE_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["quiz"] is None
    after = len(client.get("/api/quizzes", headers=host["headers"]).json())
    assert after == before


# ------------------------------------------------------------------- validation
def test_generate_requires_authentication(client, install_generator):
    install_generator(FakeGenerator([make_question()]))
    assert client.post("/api/quizzes/generate", json=BASE_PAYLOAD).status_code == 401


def test_generate_requires_topic(client, host, install_generator):
    install_generator(FakeGenerator([make_question()]))
    response = client.post(
        "/api/quizzes/generate",
        headers=host["headers"],
        json={"source_type": "topic", "question_count": 1, "save": False},
    )
    assert response.status_code == 422


def test_generate_rejects_blank_topic(client, host, install_generator):
    install_generator(FakeGenerator([make_question()]))
    response = client.post(
        "/api/quizzes/generate",
        headers=host["headers"],
        json={**BASE_PAYLOAD, "topic": "   "},
    )
    assert response.status_code == 422


def test_generate_requires_prompt_for_prompt_source(client, host, install_generator):
    install_generator(FakeGenerator([make_question()]))
    response = client.post(
        "/api/quizzes/generate",
        headers=host["headers"],
        json={"source_type": "prompt", "question_count": 1, "save": False},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("question_count", 0),
        ("question_count", 51),
        ("option_count", 1),
        ("option_count", 7),
        ("time_limit", 1),
        ("time_limit", 999),
        ("difficulty", "impossible"),
        ("source_type", "telepathy"),
        ("winners_count", 4),
    ],
)
def test_generate_rejects_out_of_range_fields(client, host, install_generator, field, value):
    install_generator(FakeGenerator([make_question()]))
    response = client.post(
        "/api/quizzes/generate",
        headers=host["headers"],
        json={**BASE_PAYLOAD, field: value},
    )
    assert response.status_code == 422


# ------------------------------------------------------------- failure handling
def test_provider_error_maps_to_502(client, host, install_generator):
    install_generator(
        FakeGenerator(error=QuizGenerationError("boom", code="AI_PROVIDER_ERROR"))
    )
    response = client.post("/api/quizzes/generate", headers=host["headers"], json=BASE_PAYLOAD)
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "AI_PROVIDER_ERROR"


def test_not_configured_maps_to_503(client, host, install_generator):
    install_generator(
        FakeGenerator(error=QuizGenerationError("no key", code="AI_NOT_CONFIGURED"))
    )
    response = client.post("/api/quizzes/generate", headers=host["headers"], json=BASE_PAYLOAD)
    assert response.status_code == 503


def test_disabled_maps_to_503(client, host, install_generator):
    install_generator(FakeGenerator(error=QuizGenerationError("off", code="AI_DISABLED")))
    response = client.post("/api/quizzes/generate", headers=host["headers"], json=BASE_PAYLOAD)
    assert response.status_code == 503


def test_no_usable_questions_maps_to_422(client, host, install_generator):
    install_generator(
        FakeGenerator(
            error=QuizGenerationError("nothing usable", code="AI_NO_VALID_QUESTIONS")
        )
    )
    response = client.post("/api/quizzes/generate", headers=host["headers"], json=BASE_PAYLOAD)
    assert response.status_code == 422


def test_failures_never_leak_provider_details(client, host, install_generator):
    install_generator(
        FakeGenerator(
            error=QuizGenerationError(
                "upstream failed: gsk_live_key_abcdef 500 from https://api.groq.com/internal",
                code="AI_PROVIDER_ERROR",
            )
        )
    )
    response = client.post("/api/quizzes/generate", headers=host["headers"], json=BASE_PAYLOAD)
    assert response.status_code == 502
    body = response.json()["detail"]
    # Only the code survives - never the upstream message, key or URL.
    assert body["code"] == "AI_PROVIDER_ERROR"
    assert "gsk_" not in response.text
    assert "api.groq.com" not in response.text
    assert "internal" not in response.text.lower()


def test_successful_response_never_contains_api_key(client, host, install_generator):
    install_generator(FakeGenerator([make_question()]))
    response = client.post("/api/quizzes/generate", headers=host["headers"], json=BASE_PAYLOAD)
    assert "gsk_" not in response.text


# -------------------------------------------------------------------- pdf path
def test_pdf_empty_upload_is_rejected(client, host, install_generator):
    install_generator(FakeGenerator([make_question()]))
    response = client.post(
        "/api/quizzes/generate/pdf",
        headers=host["headers"],
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "EMPTY_UPLOAD"


def test_pdf_unreadable_maps_to_422(client, host, install_generator):
    install_generator(FakeGenerator([make_question()]))
    response = client.post(
        "/api/quizzes/generate/pdf",
        headers=host["headers"],
        files={"file": ("broken.pdf", b"this is definitely not a pdf", "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] in {"PDF_UNREADABLE", "PDF_NO_TEXT"}


def test_pdf_requires_authentication(client, install_generator):
    install_generator(FakeGenerator([make_question()]))
    response = client.post(
        "/api/quizzes/generate/pdf",
        files={"file": ("x.pdf", b"%PDF-1.4 broken", "application/pdf")},
    )
    assert response.status_code == 401


# ------------------------------------------------- provider-agnostic helpers
def test_extract_json_handles_fenced_block():
    assert extract_json('```json\n{"questions": []}\n```') == {"questions": []}


def test_extract_json_handles_prose_around_object():
    payload = extract_json('Sure! {"questions": [{"a": 1}]} hope that helps')
    assert payload["questions"][0]["a"] == 1


def test_extract_json_rejects_non_json():
    with pytest.raises(QuizGenerationError):
        extract_json("there is no json here at all")


def test_normalise_drops_question_with_unknown_answer():
    """A correct_answer that is not among the options must never be accepted."""
    request = GenerationRequest(source_type="topic", topic="x", question_count=1)
    payload = {
        "questions": [
            {
                "question_text": "Bad?",
                "question_type": "multiple_choice",
                "options": ["a", "b", "c", "d"],
                "correct_answer": "not-an-option",
            }
        ]
    }
    with pytest.raises(QuizGenerationError) as exc:
        normalise_questions(payload, request)
    assert exc.value.code == "AI_NO_VALID_QUESTIONS"


def test_normalise_enforces_true_false_options():
    request = GenerationRequest(
        source_type="topic", topic="x", question_count=1, question_types=["true_false"]
    )
    payload = {
        "questions": [
            {
                "question_text": "Sky is blue",
                "question_type": "true_false",
                "options": ["Yes", "No"],
                "correct_answer": "True",
            }
        ]
    }
    with pytest.raises(QuizGenerationError):
        normalise_questions(payload, request)


def test_normalise_requires_two_correct_answers_for_multiple_answer():
    request = GenerationRequest(
        source_type="topic", topic="x", question_count=1, question_types=["multiple_answer"]
    )
    payload = {
        "questions": [
            {
                "question_text": "Pick two",
                "question_type": "multiple_answer",
                "options": ["a", "b", "c", "d"],
                "correct_answers": ["a"],
            }
        ]
    }
    with pytest.raises(QuizGenerationError):
        normalise_questions(payload, request)


def test_normalise_trims_to_requested_option_count():
    request = GenerationRequest(
        source_type="topic", topic="x", question_count=1, option_count=2
    )
    payload = {
        "questions": [
            {
                "question_text": "Pick one",
                "question_type": "multiple_choice",
                "options": ["a", "b", "c", "d", "e"],
                "correct_answer": "a",
                "explanation": "because",
            }
        ]
    }
    questions = normalise_questions(payload, request)
    assert len(questions[0].options) == 2
    assert questions[0].correct_answer == "a"