"""Build the final reply from retrieval results.

The model writes only the answer drawn from articles in force that are not marked as
amended. The parts that must be exact are assembled by code:

* articles amended by a text the system does not hold: the article's name, the notice
  and the referral. Their text is never shown or given to the model, since it may no
  longer be the rule in force;
* referrals for rules changed by documents the employee may not see;
* the list of sources.

The model is not called at all when there is nothing for it to answer from. Its answer
is shown only if it passes the grounding checks in ``backend.llm.verify``; otherwise the
retrieved articles are shown word for word instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.llm.client import ChatModel
from backend.llm.constants import (
    AMENDED_LABEL,
    NOT_FOUND_TEXT,
    REFERRAL_PREFIX,
    SOURCES_HEADING,
    UNVERIFIED_TEXT,
)
from backend.llm.prompts import SYSTEM_PROMPT, PromptSource, build_user_prompt
from backend.llm.verify import attach_verbatim_citations, verify_answer
from backend.retrieval.types import Candidate, RetrievalResult

_CITATION = re.compile(r"\[([0-9٠-٩]+)\]")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


@dataclass(frozen=True, slots=True)
class Source:
    """An article shown in the reply's source list."""

    number: int
    citation: str
    amended: bool = False


@dataclass(frozen=True, slots=True)
class AmendedArticle:
    """An article named with its amendment notice and referral; its text is not shown."""

    number: int
    citation: str
    notice: str


@dataclass(slots=True)
class Answer:
    """Everything shown to the employee for one question."""

    text: str = ""
    amended: list[AmendedArticle] = field(default_factory=list)
    referrals: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    # Articles shown word for word when the model's answer failed the checks.
    quoted: list[PromptSource] = field(default_factory=list)
    model_called: bool = False
    # Why the model's answer was not shown (empty when it was shown or not needed).
    rejected_reason: str = ""
    # The model's reply as received, kept for evaluation (never shown as such).
    raw_reply: str = ""

    @property
    def response_type(self) -> str:
        """answer, referral or insufficient (the categories stored in query_log)."""
        if self.text and self.text not in (NOT_FOUND_TEXT, UNVERIFIED_TEXT):
            return "answer"
        return "referral" if self.referrals or self.amended else "insufficient"


def citation_of(candidate: Candidate) -> str:
    """Document title and article label, e.g. «نظام الأحوال المدنية، المادة 34»."""
    return f"{candidate.doc_title}، {candidate.article_label}"


def _article_text(candidate: Candidate) -> str:
    return candidate.article_text or candidate.text


def _with_plain_citations(text: str) -> tuple[str, list[int]]:
    """Write citation numbers in Latin digits; return the text and the numbers cited."""
    cited: list[int] = []

    def plain(match: re.Match[str]) -> str:
        number = int(match.group(1).translate(_ARABIC_DIGITS))
        if number not in cited:
            cited.append(number)
        return f"[{number}]"

    return _CITATION.sub(plain, text).strip(), sorted(cited)


def compose_answer(question: str, result: RetrievalResult, model: ChatModel) -> Answer:
    """Number the retrieved articles, ask the model about the plain ones, assemble the rest."""
    answer = Answer(referrals=[referral.referral_text for referral in result.referrals])
    plain: list[PromptSource] = []
    for number, candidate in enumerate(result.chunks, start=1):
        notice = result.amended_notices.get(candidate.chunk_id)
        if notice:
            answer.amended.append(AmendedArticle(number, citation_of(candidate), notice))
            continue
        titles = result.changed_by.get(candidate.chunk_id, [])
        note = f"(عُدّل حكم هذه المادة بموجب: {'، '.join(titles)})" if titles else ""
        plain.append(PromptSource(number, citation_of(candidate), _article_text(candidate), note))

    if plain:
        reply = model.complete(SYSTEM_PROMPT, build_user_prompt(question, plain))
        answer.model_called = True
        answer.raw_reply = reply
        if NOT_FOUND_TEXT in reply:
            answer.text = NOT_FOUND_TEXT
        else:
            texts = {source.number: f"{source.citation}\n{source.text}" for source in plain}
            text, _ = _with_plain_citations(reply)
            text, cited = _with_plain_citations(
                attach_verbatim_citations(text, {s.number: s.text for s in plain})
            )
            verdict = verify_answer(text, texts)
            if verdict.ok:
                answer.text = text
                answer.sources = [
                    Source(source.number, source.citation)
                    for source in plain
                    if source.number in cited
                ]
            else:
                answer.text = UNVERIFIED_TEXT
                answer.rejected_reason = verdict.reason
                answer.quoted = plain
                answer.sources = [Source(source.number, source.citation) for source in plain]
    elif not answer.amended and not answer.referrals:
        answer.text = NOT_FOUND_TEXT

    answer.sources += [Source(item.number, item.citation, amended=True) for item in answer.amended]
    answer.sources.sort(key=lambda source: source.number)
    if answer.text == NOT_FOUND_TEXT and (answer.amended or answer.referrals):
        answer.text = ""
    return answer


def render(answer: Answer) -> str:
    """The reply as plain text, in the order the employee reads it."""
    blocks: list[str] = []
    if answer.text:
        blocks.append(answer.text)
    for source in answer.quoted:
        blocks.append(f"[{source.number}] {source.citation}\n«{source.text}»")
    blocks += [f"[{item.number}] {item.citation}\n{item.notice}" for item in answer.amended]
    blocks += [f"{REFERRAL_PREFIX}: {text}" for text in answer.referrals]
    if answer.sources:
        lines = [f"{SOURCES_HEADING}:"]
        for source in answer.sources:
            label = f" {AMENDED_LABEL}" if source.amended else ""
            lines.append(f"[{source.number}] {source.citation}{label}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
