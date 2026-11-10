"""Tests for the HTTP API wiring, with the database and models replaced by fakes."""

from __future__ import annotations

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from backend.api import routes
from backend.llm.answer import compose_answer
from backend.llm.client import LLMError
from backend.llm.service import AskResult, cited_chunk_ids
from backend.main import app
from backend.retrieval.queries import UnknownEmployeeError
from backend.retrieval.types import Candidate, RetrievalResult
from backend.services.access import (
    AccessDecision,
    AccessLookupError,
    next_step,
)

NOTICE = "⚠ تنبيه: هذه المادة عليها تعديلات. يُرجى الرجوع إلى الإدارة القانونية."


def _article(chunk_id: str, number: int, text: str) -> Candidate:
    return Candidate(chunk_id, "بند", 2, "اللائحة", number, number, f"المادة {number}", 1,
                     article_text=text)


class FakeModel:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    def complete(self, system: str, user: str) -> str:
        return self.reply


class FakeService:
    """Stands in for AnswerService: fixed retrieval, fixed model reply, no database."""

    def __init__(self, reply: str = "المدة ثلاثون يومًا [1].", error: Exception | None = None):
        self.reply, self.error = reply, error

    def ask(self, employee_id: str, question: str) -> AskResult:
        if self.error:
            raise self.error
        result = RetrievalResult(
            chunks=[_article("C87", 87, "داخل المدن ثلاثين يوما"), _article("C34", 34, "نص قديم")],
            amended_notices={"C34": NOTICE},
        )
        answer = compose_answer(question, result, FakeModel(self.reply))
        return AskResult(answer, result, "fake-model", 1.5, 7)


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_ask_returns_checked_answer_amended_notice_and_sources(client: TestClient) -> None:
    app.dependency_overrides[routes.get_answer_service] = lambda: FakeService()

    body = client.post("/api/ask", json={"employee_id": "E001", "question": "كم المدة؟"}).json()

    assert body["response_type"] == "answer"
    assert body["answer"] == "المدة ثلاثون يومًا [1]."
    assert body["verified"] is True
    assert body["amended"] == [{"number": 2, "citation": "اللائحة، المادة 34", "notice": NOTICE}]
    assert [s["number"] for s in body["sources"]] == [1, 2]
    assert "نص قديم" not in body["reply"]
    assert (body["query_id"], body["model"]) == (7, "fake-model")


def test_ask_with_rejected_answer_quotes_the_articles(client: TestClient) -> None:
    app.dependency_overrides[routes.get_answer_service] = lambda: FakeService("المدة 13 يومًا.")

    body = client.post("/api/ask", json={"employee_id": "E001", "question": "كم المدة؟"}).json()

    assert body["verified"] is False
    assert body["quoted"][0]["text"] == "داخل المدن ثلاثين يوما"


@pytest.mark.parametrize(
    ("error", "status"),
    [(UnknownEmployeeError("x"), 404), (LLMError("down"), 503)],
)
def test_ask_errors(client: TestClient, error: Exception, status: int) -> None:
    app.dependency_overrides[routes.get_answer_service] = lambda: FakeService(error=error)

    response = client.post("/api/ask", json={"employee_id": "E9", "question": "سؤال تجريبي"})

    assert response.status_code == status


def test_ask_rejects_an_empty_question(client: TestClient) -> None:
    response = client.post("/api/ask", json={"employee_id": "E001", "question": ""})

    assert response.status_code == 422


def test_access_returns_the_matrix_decision(client: TestClient, monkeypatch) -> None:
    decision = AccessDecision(
        request_id=3, employee_id="E001", role_name="كاتب السجل", resource_id="RS001",
        resource_name="السجل المدني المركزي", classification="سري", action_id="A4",
        action_name="مشاركة", decision="denied", decision_label="مرفوض", status="auto",
        approver=None, explanation="لا يجوز نقلها", legal_basis="حكم نظامي خاص",
        article="نظام الأحوال المدنية، المادة 11", next_step="غير جائز", rule_id="DR00004",
    )
    monkeypatch.setattr(routes, "decide_access", lambda *args: decision)
    app.dependency_overrides[routes.get_session] = lambda: None

    body = client.post(
        "/api/access", json={"employee_id": "E001", "resource_id": "RS001", "action_id": "A4"}
    ).json()

    assert (body["decision"], body["status"], body["request_id"]) == ("denied", "auto", 3)
    assert body["article"] == "نظام الأحوال المدنية، المادة 11"


def test_access_unknown_resource_is_404(client: TestClient, monkeypatch) -> None:
    def fail(*args):
        raise AccessLookupError("Unknown resource")

    monkeypatch.setattr(routes, "decide_access", fail)
    app.dependency_overrides[routes.get_session] = lambda: None

    response = client.post(
        "/api/access", json={"employee_id": "E001", "resource_id": "X", "action_id": "A1"}
    )

    assert response.status_code == 404


def test_next_step_wording() -> None:
    assert next_step("allowed", "عرض المورد", None, False) == "عرض المورد"
    assert "رئيس المكتب" in next_step("requires_approval", "", "رئيس المكتب", False)
    assert next_step("denied", "", None, True) == "هذا الإجراء غير جائز نظامًا على هذا المورد."
    assert "صلاحيات دورك" in next_step("denied", "", None, False)


def test_cited_chunk_ids_follow_the_source_numbers() -> None:
    answer = FakeService().ask("E001", "كم المدة؟").answer
    result = RetrievalResult(chunks=[_article("C87", 87, ""), _article("C34", 34, "")])

    assert cited_chunk_ids(answer, result) == ["C87", "C34"]
