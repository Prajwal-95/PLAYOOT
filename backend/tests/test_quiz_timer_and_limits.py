"""Options-per-question selector, editable timers and the 50-question ceiling.

Three things have to stay in step:

* the "Options per Question" control must offer every count the backend
  accepts (2..6) and must actually let the user pick one,
* EDIT QUIZ must expose the SAME timer control as CREATE QUIZ, and a new
  value has to survive save -> reload -> a game created from that quiz,
* one generation request may ask for 1..50 questions.  51 has to be refused
  by the BACKEND, not merely hidden by the frontend, and asking for 50 must
  really produce 50 rather than quietly being capped at an older limit.

There is no JS test runner in this repository, so the UI half is asserted at
source level the same way the rest of this suite does it - comments are
stripped first, so prose like "// don't cap the value" cannot satisfy a guard.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ai.base import (
    GeneratedQuestion,
    GenerationRequest,
    MAX_QUESTIONS_PER_CALL,
    MAX_QUESTIONS_PER_QUIZ,
    QuizGenerationError,
)
from app.ai.groq_generator import GroqQuizGenerator
from app.schemas.api import GenerateQuizIn, QuestionIn

BACKEND_DIR = Path(__file__).resolve().parents[1]
FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _accepts(model, **kwargs) -> bool:
    """Would the schema let this value through? (avoids poking Field internals)"""
    from pydantic import ValidationError

    try:
        model(**kwargs)
        return True
    except ValidationError:
        return False


# ------------------------------------------------------------------ source IO
def _strip_comments(source: str) -> str:
    """Drop //, /* */ and JSX {/* */} comments (see test_share_link.py)."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    kept = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("//", "*", "/*")):
            continue
        line = re.sub(r"\s//[^/].*$", "", line)
        kept.append(line)
    return "\n".join(kept)


def _code(name: str) -> str:
    path = FRONTEND_SRC / name
    if not path.exists():
        pytest.skip("frontend sources are not available in this checkout")
    return _strip_comments(path.read_text(encoding="utf-8-sig"))


def _backend_file(name: str) -> str:
    return (BACKEND_DIR / name).read_text(encoding="utf-8")


def _const_int(name: str) -> int:
    match = re.search(rf"export const {name} = (\d+);", _code("services/api.ts"))
    assert match, f"export const {name} not found in services/api.ts"
    return int(match.group(1))


def _const_list(name: str) -> list[int]:
    match = re.search(rf"export const {name} = \[([^\]]*)\]", _code("services/api.ts"))
    assert match, f"export const {name} not found in services/api.ts"
    return [int(part) for part in match.group(1).split(",") if part.strip()]


# --------------------------------------------------------- generation fixtures
BASE_PAYLOAD = {
    "source_type": "topic",
    "topic": "World Capitals",
    "question_count": 2,
    "difficulty": "mixed",
    "option_count": 4,
    "save": False,
}


def make_question(text: str = "Capital of France?") -> GeneratedQuestion:
    return GeneratedQuestion(
        question_text=text,
        question_type="multiple_choice",
        options=["Paris", "Rome", "Berlin", "Madrid"],
        correct_answer="Paris",
        correct_answers=[],
        explanation="Paris has been the capital since 987.",
        time_limit=20,
        points=1000,
    )


class FakeGenerator:
    def __init__(self, questions: list[GeneratedQuestion]):
        self._questions = questions
        self.requests: list[GenerationRequest] = []

    @property
    def provider(self) -> str:
        return "fake"

    async def generate(self, request: GenerationRequest):
        self.requests.append(request)
        return list(self._questions)


@pytest.fixture
def install_generator(monkeypatch):
    import app.api.routes_quiz as routes_quiz

    def _install(questions):
        generator = FakeGenerator(questions)
        monkeypatch.setattr(routes_quiz, "get_quiz_generator", lambda: generator)
        return generator

    return _install


def _generate(client, host, install_generator, **overrides):
    count = int(overrides.get("question_count", BASE_PAYLOAD["question_count"]))
    generator = install_generator([make_question(f"Question {i}?") for i in range(count)])
    response = client.post(
        "/api/quizzes/generate",
        headers=host["headers"],
        json={**BASE_PAYLOAD, **overrides},
    )
    return response, generator


# ----------------------------------------------------------- quiz edit helpers
def _put_timer(quiz_id: int, host: dict, client, **timers: int):
    """Read the quiz, change only ``time_limit`` and PUT the whole thing back.

    Mirrors exactly what Edit Quiz sends: title, description, winners_count and
    the full question array.
    """
    current = client.get(f"/api/quizzes/{quiz_id}", headers=host["headers"])
    assert current.status_code == 200, current.text
    body = current.json()

    questions = [dict(q) for q in body["questions"]]
    for key, value in timers.items():
        index = int(key[1:])
        questions[index] = {**questions[index], "time_limit": value}

    return client.put(
        f"/api/quizzes/{quiz_id}",
        headers=host["headers"],
        json={
            "title": body["title"],
            "description": body["description"],
            "questions": questions,
            "winners_count": body.get("winners_count") or 3,
        },
    )


def _db_time_limits(quiz_id: int) -> list[int]:
    """The stored timers - exactly what a future game will load."""
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.quiz import Question

    async def _query() -> list[int]:
        async with SessionLocal() as session:
            rows = await session.scalars(
                select(Question)
                .where(Question.quiz_id == quiz_id)
                .order_by(Question.order_index)
            )
            return [int(row.time_limit) for row in rows]

    return asyncio.run(_query())


# ===========================================================================
# 1. OPTIONS PER QUESTION - the selector
# ===========================================================================
def test_selector_lists_every_supported_option_count(client, host, install_generator):
    """2..6 are the only counts the backend accepts, and the list shows all."""
    assert _const_list("OPTION_COUNTS") == [2, 3, 4, 5, 6]
    assert _const_int("MIN_OPTION_COUNT") == 2
    assert _const_int("MAX_OPTION_COUNT") == 6

    create = _code("pages/CreateQuizPage.tsx")
    assert "<ScrollSelect" in create
    assert "options={OPTION_COUNTS}" in create
    assert 'label="Options per Question"' in create

    assert _accepts(GenerateQuizIn, topic="x", option_count=2)
    assert _accepts(GenerateQuizIn, topic="x", option_count=6)
    assert not _accepts(GenerateQuizIn, topic="x", option_count=1)
    assert not _accepts(GenerateQuizIn, topic="x", option_count=7)

    for count in (2, 3, 4, 5, 6):
        response, generator = _generate(
            client, host, install_generator, question_count=1, option_count=count
        )
        assert response.status_code == 200, f"option_count={count}: {response.text}"
        assert generator.requests[-1].option_count == count


def test_selected_option_count_stays_in_form_state():
    """Clicking a row writes that value straight into ``optionCount``."""
    create = _code("pages/CreateQuizPage.tsx")
    assert "const [optionCount, setOptionCount]" in create
    assert re.search(r"useState\(4\)", create)
    # the row hands its own value to the setter...
    scroll = _code("components/ui/ScrollSelect.tsx")
    assert "onClick={() => onChange(option)}" in scroll
    assert "aria-selected={selected}" in scroll
    # ...Create Quiz passes the setter down and reads the value back out
    assert "onChange={setOptionCount}" in create
    assert "value={optionCount}" in create
    assert "option_count: optionCount" in create
    assert 'formData.append("option_count", String(optionCount))' in create


def test_invalid_option_count_is_still_rejected(client, host, install_generator):
    for value in (1, 7):
        response, _ = _generate(
            client, host, install_generator, question_count=1, option_count=value
        )
        assert response.status_code == 422, f"option_count={value} must be rejected"

    # and the UI never even offers to send one
    create = _code("pages/CreateQuizPage.tsx")
    assert (
        "optionCount < MIN_OPTION_COUNT || optionCount > MAX_OPTION_COUNT" in create
    )


def test_option_selector_is_scrollable_and_cannot_be_clipped():
    """A bounded in-page list: scrolls inside itself, never off the screen."""
    scroll = _code("components/ui/ScrollSelect.tsx")

    # bounded height + its own scrollbar -> the page never has to scroll
    assert "overflow-y-auto" in scroll
    assert re.search(r"max-h-\d+", scroll), "the list must have a max height"
    assert "overscroll-contain" in scroll

    # normal document flow: no absolute/fixed layer for an overflow:hidden
    # ancestor to clip or cover.
    match = re.search(
        r'role="listbox"[\s\S]{0,600}?className=\{cn\(([\s\S]*?)\)\}', scroll
    )
    assert match, "the listbox element must declare its own classes"
    classes = match.group(1)
    for banned in ("absolute", "fixed", "hidden", "overflow-hidden", "opacity-0",
                   "pointer-events-none"):
        assert banned not in classes, f"listbox must not use `{banned}`"

    # and it is actually mounted on the create page
    assert "<ScrollSelect" in _code("pages/CreateQuizPage.tsx")


# ===========================================================================
# 2. EDIT QUIZ - the timer
# ===========================================================================
def _function_body(source: str, name: str) -> str:
    match = re.search(rf"const {name} = \([\s\S]*?\n  \}};", source)
    assert match, f"{name} not found"
    return match.group(0)


def test_existing_timer_is_loaded_into_the_edit_form():
    edit = _code("pages/QuizViewPage.tsx")

    handle_edit = _function_body(edit, "handleEditQuestion")
    assert "time_limit: q.time_limit" in handle_edit, (
        "the edit form must be seeded from the loaded question"
    )
    # ...and the control renders that form value
    assert "value={form.time_limit}" in edit


def test_timer_control_is_editable_and_reaches_the_form_state():
    edit = _code("pages/QuizViewPage.tsx")

    # the SAME shared control CREATE QUIZ uses, on the same presets
    assert 'from "../components/ui/SelectWithCustom"' in edit
    assert "presets={TIMER_PRESETS}" in edit
    assert 'unit="sec"' in edit
    # control -> handler -> editForm / quiz.questions
    assert "onTimeLimitChange(" in edit
    handle_time = _function_body(edit, "handleTimeLimitChange")
    assert "time_limit: value" in handle_time
    # typing must never blank or snap the field
    assert "clampInt(" in edit
    # ...and "Save Changes" cannot drop an open card's pending edit
    assert "commitPendingEdit" in edit


def test_timer_update_reaches_the_backend(client, host, quiz):
    response = _put_timer(quiz["id"], host, client, q0=45)
    assert response.status_code == 200, response.text
    assert response.json()["questions"][0]["time_limit"] == 45


def test_timer_update_persists_after_reload(client, host, quiz):
    assert _put_timer(quiz["id"], host, client, q0=90).status_code == 200

    reloaded = client.get(f"/api/quizzes/{quiz['id']}", headers=host["headers"])
    assert reloaded.status_code == 200
    saved = reloaded.json()["questions"]
    assert saved[0]["time_limit"] == 90
    # a neighbour's timer is untouched...
    assert saved[1]["time_limit"] == 5
    # ...and so is the rest of the edited question
    original = quiz["questions"][0]
    for field in ("question_text", "options", "correct_answer", "explanation", "points"):
        assert saved[0][field] == original[field], field
    assert _db_time_limits(quiz["id"])[0] == 90


def test_future_game_uses_the_updated_timer(client, host, quiz):
    assert _put_timer(quiz["id"], host, client, q0=75).status_code == 200

    created = client.post(
        "/api/games",
        headers=host["headers"],
        json={"quiz_id": quiz["id"], "mode": "individual"},
    )
    assert created.status_code == 201, created.text

    # engine.start_game reads Question.time_limit straight from these rows
    assert _db_time_limits(quiz["id"]) == [75, 5]


def test_invalid_timer_is_rejected(client, host, quiz):
    for value in (4, 0, -1, 301, 10_000):
        response = _put_timer(quiz["id"], host, client, q0=value)
        assert response.status_code == 422, f"time_limit={value}: {response.text}"


def test_create_and_edit_expose_identical_timer_values():
    """CREATE TIMER OPTIONS == EDIT TIMER OPTIONS, and both match the schema."""
    assert _const_list("TIMER_PRESETS") == [5, 10, 15, 20, 30, 60, 120, 180]
    assert _const_int("TIMER_MIN") == 5
    assert _const_int("TIMER_MAX") == 300

    field = QuestionIn.model_fields["time_limit"]
    assert field is not None
    base = {"question_text": "abc", "options": ["A", "B"], "correct_answer": "A"}
    for value in (5, 10, 15, 20, 30, 60, 120, 180, 300):
        assert _accepts(QuestionIn, time_limit=value, **base), value
    assert not _accepts(QuestionIn, time_limit=4, **base)
    assert not _accepts(QuestionIn, time_limit=301, **base)

    for name in ("pages/CreateQuizPage.tsx", "pages/QuizViewPage.tsx"):
        source = _code(name)
        assert "presets={TIMER_PRESETS}" in source, name
        assert "TIMER_MIN" in source and "TIMER_MAX" in source, name
        assert 'from "../components/ui/SelectWithCustom"' in source, name
        # neither page may keep its own (differing) hard-coded preset list
        assert not re.search(r"presets=\{\[[\d,\s]+\]\}", source), name


# ===========================================================================
# 3. MAXIMUM GENERATED QUESTIONS = 50
# ===========================================================================
def test_one_question_is_accepted(client, host, install_generator):
    response, generator = _generate(
        client, host, install_generator, question_count=1
    )
    assert response.status_code == 200, response.text
    assert generator.requests[-1].question_count == 1


@pytest.mark.parametrize("count", [5, 10, 20, 30, 40])
def test_normal_question_counts_are_accepted(client, host, install_generator, count):
    response, generator = _generate(
        client, host, install_generator, question_count=count
    )
    assert response.status_code == 200, response.text
    assert generator.requests[-1].question_count == count


def test_fifty_questions_is_accepted(client, host, install_generator):
    response, generator = _generate(
        client, host, install_generator, question_count=50
    )
    assert response.status_code == 200, response.text
    assert generator.requests[-1].question_count == 50
    assert response.json()["generated_count"] == 50


def test_fifty_one_questions_is_rejected_by_the_backend(client, host, install_generator):
    response, _ = _generate(client, host, install_generator, question_count=51)
    assert response.status_code == 422, response.text


def test_backend_bounds_are_one_to_fifty():
    assert GenerateQuizIn.model_fields["question_count"] is not None
    assert MAX_QUESTIONS_PER_QUIZ == 50

    assert _accepts(GenerateQuizIn, topic="x", question_count=1)
    assert _accepts(GenerateQuizIn, topic="x", question_count=50)
    assert not _accepts(GenerateQuizIn, topic="x", question_count=0)
    assert not _accepts(GenerateQuizIn, topic="x", question_count=51)

    with pytest.raises(Exception) as excinfo:
        GenerateQuizIn(question_count=51, topic="x")
    assert "less than or equal to 50" in str(excinfo.value)


def test_frontend_cannot_select_more_than_fifty():
    api = _code("services/api.ts")
    assert _const_int("MAX_GENERATED_QUESTIONS") == 50
    assert _const_int("MIN_GENERATED_QUESTIONS") == 1
    assert "MAX_GENERATED_QUESTIONS" in api

    create = _code("pages/CreateQuizPage.tsx")
    assert "max={MAX_GENERATED_QUESTIONS}" in create
    assert re.search(
        r"clampInt\(\s*e\.target\.value,\s*questionCount,\s*"
        r"MIN_GENERATED_QUESTIONS,\s*MAX_GENERATED_QUESTIONS\s*\)",
        create,
    ), "the question-count input must clamp against the shared constant"
    # the old hard ceiling is gone
    assert "max={20}" not in create
    assert "Math.min(20," not in create
    # and a value outside the range never leaves the browser
    assert (
        "questionCount < MIN_GENERATED_QUESTIONS "
        "|| questionCount > MAX_GENERATED_QUESTIONS" in create
    )


def test_every_backend_enforcement_point_now_says_fifty():
    schema = _backend_file("app/schemas/api.py")
    assert (
        "question_count: int = Field(default=5, ge=1, le=MAX_QUESTIONS_PER_QUIZ)"
        in schema
    )
    assert "ge=1, le=20" not in schema

    routes = _backend_file("app/api/routes_quiz.py")
    assert "count > MAX_QUESTIONS_PER_QUIZ" in routes, (
        "the PDF path must reject an oversized count too"
    )
    assert "min(int(question_count), 20)" not in routes
    assert "le=20" not in routes


# ---------------------------------------------------------------- groq itself
def _install_fake_groq(monkeypatch, *, per_call: int = 10):
    """Stand in for the Groq SDK.

    Every ``create`` call honours the count the prompt asked for, capped at
    ``per_call`` - which is exactly how a provider that truncates at
    ``max_tokens`` behaves. Returns the list of calls it received.
    """
    pytest.importorskip("groq")
    import groq

    produced = {"total": 0}
    calls: list[dict] = []

    async def create(**kwargs):
        calls.append(kwargs)
        asked = int(
            re.search(
                r"Produce exactly (\d+) questions", kwargs["messages"][0]["content"]
            ).group(1)
        )
        count = min(asked, per_call)
        questions = [
            {
                "question_text": f"Generated question {produced['total'] + i}?",
                "question_type": "multiple_choice",
                "options": ["Paris", "Rome", "Berlin", "Madrid"],
                "correct_answer": "Paris",
                "explanation": "Because it is.",
            }
            for i in range(count)
        ]
        produced["total"] += count
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps({"questions": questions})
                    )
                )
            ]
        )

    class _Client:
        def __init__(self, *args, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    monkeypatch.setattr(groq, "AsyncGroq", _Client)
    return calls


def _generator() -> GroqQuizGenerator:
    return GroqQuizGenerator(
        api_key="test-key",
        model="test-model",
        max_attempts=1,
        retry_base_delay=0,
    )


def _generate_question_count_of(calls: list[dict]) -> list[int]:
    return [
        int(
            re.search(
                r"Produce exactly (\d+) questions", call["messages"][0]["content"]
            ).group(1)
        )
        for call in calls
    ]


def test_ai_generation_can_actually_produce_all_fifty(monkeypatch):
    """50 requested -> 50 returned, in rounds of at most 10 questions each."""
    calls = _install_fake_groq(monkeypatch, per_call=10)

    result = asyncio.run(
        _generator().generate(
            GenerationRequest(source_type="topic", topic="Trivia", question_count=50)
        )
    )

    assert len(result) == 50
    assert len({q.question_text for q in result}) == 50

    asked = _generate_question_count_of(calls)
    assert max(asked) <= MAX_QUESTIONS_PER_CALL, "never one truncatable mega-call"
    assert sum(asked) >= 50
    assert len(calls) > 1, "a 50-question quiz must be requested in rounds"


def test_generation_never_silently_returns_a_shorter_quiz(monkeypatch):
    """A provider that keeps under-producing is reported, not swallowed."""
    _install_fake_groq(monkeypatch, per_call=1)

    with pytest.raises(QuizGenerationError) as excinfo:
        asyncio.run(
            _generator().generate(
                GenerationRequest(source_type="topic", topic="Trivia", question_count=20)
            )
        )
    assert excinfo.value.code == "AI_INCOMPLETE"
    assert "20" in excinfo.value.message


def test_first_round_failure_is_still_reported_as_no_usable_questions(monkeypatch):
    _install_fake_groq(monkeypatch, per_call=0)

    with pytest.raises(QuizGenerationError) as excinfo:
        asyncio.run(
            _generator().generate(
                GenerationRequest(source_type="topic", topic="Trivia", question_count=5)
            )
        )
    assert excinfo.value.code == "AI_NO_VALID_QUESTIONS"
