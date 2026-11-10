"""Tests for composing answers: what the model sees and what code assembles itself."""

from __future__ import annotations

from backend.llm.answer import compose_answer, render
from backend.llm.client import _THINKING
from backend.llm.constants import NOT_FOUND_TEXT, UNVERIFIED_TEXT
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


def test_amended_article_is_named_with_notice_but_its_text_is_never_shown() -> None:
    result = RetrievalResult(
        chunks=[
            article("A87", 87, text="نص المادة 87: ثلاثين يوما"),
            article("A34", 34, "النظام", "خمسة عشر يوما"),
        ],
        amended_notices={"A34": NOTICE},
    )
    model = FakeModel("المدة ثلاثون يومًا [1].")

    answer = compose_answer("كم المدة؟", result, model)

    assert "خمسة عشر" not in model.prompts[0]
    assert answer.text == "المدة ثلاثون يومًا [1]."
    text = render(answer)
    assert "خمسة عشر" not in text
    assert f"[2] النظام، المادة 34\n{NOTICE}" in text
    assert "[2] النظام، المادة 34 (معدّلة)" in text
    assert answer.response_type == "answer"


def test_only_amended_articles_do_not_call_the_model() -> None:
    result = RetrievalResult(chunks=[article("A34", 34)], amended_notices={"A34": NOTICE})
    model = FakeModel("لا يُستخدم")

    answer = compose_answer("سؤال", result, model)

    assert model.prompts == []
    assert answer.text == ""
    assert "نص المادة 34" not in render(answer)
    assert answer.response_type == "referral"


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


def test_grounded_answer_is_shown_with_only_its_cited_sources() -> None:
    result = RetrievalResult(
        chunks=[article("A87", 87, text="داخل المدن ثلاثين يوما"), article("A88", 88)]
    )
    answer = compose_answer("سؤال", result, FakeModel("المدة داخل المدن ثلاثون يومًا [١]."))

    assert answer.text == "المدة داخل المدن ثلاثون يومًا [1]."
    assert [source.number for source in answer.sources] == [1]
    assert answer.rejected_reason == ""


def test_invented_number_is_not_shown_and_articles_are_quoted() -> None:
    """The model said 13 days; no source says 13, so the articles are shown instead."""
    result = RetrievalResult(chunks=[article("A87", 87, text="داخل المدن ثلاثين يوما")])
    answer = compose_answer("سؤال", result, FakeModel("المدة ثلاثة عشر يومًا [1]."))

    assert answer.text == UNVERIFIED_TEXT
    assert "13" in answer.rejected_reason
    text = render(answer)
    assert "«داخل المدن ثلاثين يوما»" in text
    assert "ثلاثة عشر" not in text
    assert answer.response_type == "insufficient"


def test_answer_without_citations_is_not_shown() -> None:
    result = RetrievalResult(chunks=[article("A87", 87, text="ثلاثين يوما")])
    answer = compose_answer("سؤال", result, FakeModel("المدة ثلاثون يومًا حسب الولاية."))

    assert answer.text == UNVERIFIED_TEXT
    assert "without a source" in answer.rejected_reason


def test_citation_to_a_source_not_given_is_not_shown() -> None:
    result = RetrievalResult(chunks=[article("A87", 87, text="ثلاثين يوما")])
    answer = compose_answer("سؤال", result, FakeModel("المدة ثلاثون يومًا [7]."))

    assert answer.text == UNVERIFIED_TEXT


def test_model_saying_not_found_lists_no_sources() -> None:
    result = RetrievalResult(chunks=[article("A87", 87)])
    answer = compose_answer("سؤال", result, FakeModel(NOT_FOUND_TEXT))

    assert answer.sources == []
    assert answer.response_type == "insufficient"


def test_thinking_section_is_removed() -> None:
    assert _THINKING.sub("", "<think>أفكر\nهنا</think>الجواب").strip() == "الجواب"


def test_client_sends_reasoning_effort_and_reports_server_errors() -> None:
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    import pytest

    from backend.llm.client import LLMError, OpenAICompatibleModel

    bodies: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            bodies.append(body)
            if body["model"] == "missing":
                self.send_response(404)
                payload = b'{"error":"model not found"}'
            else:
                self.send_response(200)
                payload = json.dumps(
                    {"choices": [{"message": {"content": "<think>x</think>الجواب [1]."}}]}
                ).encode()
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/v1"
    try:
        reply = OpenAICompatibleModel(url, "m", reasoning_effort="none").complete("s", "u")
        assert reply == "الجواب [1]."
        assert bodies[0]["reasoning_effort"] == "none"
        OpenAICompatibleModel(url, "m").complete("s", "u")
        assert "reasoning_effort" not in bodies[1]
        with pytest.raises(LLMError, match="model not found"):
            OpenAICompatibleModel(url, "missing").complete("s", "u")
    finally:
        server.shutdown()


def test_number_words_and_compounds_are_read() -> None:
    from backend.llm.verify import numbers_in

    text = "خمسة عشر يوما وثلاثين يومًا وخمسين كيلا وثمانية عشرة عاماً والمادة (34)"
    assert numbers_in(text) == {15, 30, 50, 18, 34}
    assert numbers_in("أحد الوالدين أو أحد عشر شخصًا") == {11}
    assert numbers_in("خمسة وعشرون") == {25}


def test_uncited_sentence_copied_from_a_source_gets_its_number() -> None:
    """ALLaM copied article 88 word for word without [1]; the code adds the number."""
    text = "تكون مدة التبليغ عن واقعات الميلاد المنصوص عليها بالمادة (35) من النظام ثلاثين يوما."
    result = RetrievalResult(chunks=[article("A87", 87, text="داخل المدن"), article("A88", 88, text=text)])

    answer = compose_answer("سؤال", result, FakeModel(text))

    assert answer.text == text[:-1] + " [2]."
    assert [source.number for source in answer.sources] == [2]
    assert answer.raw_reply == text


def test_reworded_or_short_uncited_sentences_get_no_number() -> None:
    from backend.llm.verify import attach_verbatim_citations

    sources = {1: "تكون مدة التبليغ عن واقعات الميلاد داخل المدن ثلاثين يوما."}
    assert attach_verbatim_citations("المدة ثلاثون يومًا للمواليد في المدن.", sources) == (
        "المدة ثلاثون يومًا للمواليد في المدن."
    )
    assert attach_verbatim_citations("ثلاثين يوما.", sources) == "ثلاثين يوما."


def test_evaluation_scores_cited_and_expected_articles() -> None:
    from backend.llm.evaluate import score

    case = {"expect": "answer", "expected": [{"doc": "اللائحة", "article": 87}]}
    result = RetrievalResult(chunks=[article("A87", 87, text="ثلاثين يوما"), article("A88", 88)])
    answer = compose_answer("سؤال", result, FakeModel("المدة ثلاثون يومًا [1]."))

    scored = score(case, result, answer)

    assert scored["expected_retrieved"] is True
    assert scored["expected_cited"] is True
    assert scored["type_ok"] is True
    assert scored["cited"] == ["اللائحة:87"]
