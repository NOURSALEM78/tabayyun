"""Tests for composing answers: what the model sees and what code assembles itself."""

from __future__ import annotations

from backend.llm.answer import compose_answer, render
from backend.llm.client import _THINKING
from backend.llm.constants import NOT_FOUND_TEXT
from backend.retrieval.types import Candidate, Referral, RetrievalResult

NOTICE = "⚠ تنبيه: هذه المادة عليها تعديلات. يُرجى الرجوع إلى الإدارة القانونية."


class FakeModel:
    """Returns a fixed reply and records the prompts it was given."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.prompts.append(user)
        return self.reply


def article(chunk_id: str, number: int, title: str = "اللائحة", text: str = "") -> Candidate:
    return Candidate(
        chunk_id, "بند", 2, title, number, number, f"المادة {number}", 1,
        article_text=text or f"نص المادة {number}",
    )


def test_model_sees_plain_articles_only_and_code_quotes_the_amended_one() -> None:
    result = RetrievalResult(
        chunks=[article("A87", 87), article("A34", 34, "النظام", "خمسة عشر يوما")],
        amended_notices={"A34": NOTICE},
    )
    model = FakeModel("المدة ثلاثون يومًا [1].")

    answer = compose_answer("كم المدة؟", result, model)

    assert "نص المادة 87" in model.prompts[0]
    assert "خمسة عشر" not in model.prompts[0]
    assert answer.amended[0].text == "خمسة عشر يوما"
    text = render(answer)
    assert "نص المادة كما ورد: «خمسة عشر يوما»" in text
    assert "[2] النظام، المادة 34 (معدّلة)" in text
    assert answer.response_type == "answer"


def test_only_amended_articles_do_not_call_the_model() -> None:
    result = RetrievalResult(chunks=[article("A34", 34)], amended_notices={"A34": NOTICE})
    model = FakeModel("لا يُستخدم")

    answer = compose_answer("سؤال", result, model)

    assert model.prompts == []
    assert answer.text == ""
    assert answer.response_type == "answer"


def test_referral_only_does_not_call_the_model() -> None:
    result = RetrievalResult(referrals=[Referral("الوكالة", "يُرجى الرجوع إلى الوكالة.", (87,))])
    model = FakeModel("لا يُستخدم")

    answer = compose_answer("سؤال", result, model)

    assert model.prompts == []
    assert render(answer) == "إحالة: يُرجى الرجوع إلى الوكالة."
    assert answer.response_type == "referral"


def test_nothing_retrieved_is_insufficient_without_the_model() -> None:
    answer = compose_answer("سؤال", RetrievalResult(), FakeModel("لا يُستخدم"))

    assert answer.text == NOT_FOUND_TEXT
    assert answer.response_type == "insufficient"


def test_citations_to_missing_sources_are_removed() -> None:
    result = RetrievalResult(chunks=[article("A87", 87), article("A88", 88)])
    answer = compose_answer("سؤال", result, FakeModel("المدة ثلاثون يومًا [٢] [7]."))

    assert answer.text == "المدة ثلاثون يومًا [2]."
    assert [source.number for source in answer.sources] == [2]


def test_model_saying_not_found_lists_no_sources() -> None:
    result = RetrievalResult(chunks=[article("A87", 87)])
    answer = compose_answer("سؤال", result, FakeModel(NOT_FOUND_TEXT))

    assert answer.sources == []
    assert answer.response_type == "insufficient"


def test_thinking_section_is_removed() -> None:
    assert _THINKING.sub("", "<think>أفكر\nهنا</think>الجواب").strip() == "الجواب"
