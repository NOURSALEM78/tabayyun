"""Build the final reply from retrieval results.

The model writes only the answer drawn from articles in force that are not marked as
amended. The parts that must be exact are assembled by code:

* articles amended by a text the system does not hold: the notice, the article quoted
  word for word from the database, and the referral;
* referrals for rules changed by documents the employee may not see;
* the list of sources.

The model is not called at all when there is nothing for it to answer from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.llm.client import ChatModel
from backend.llm.constants import (
    AMENDED_LABEL,
    AMENDED_TEXT_PREFIX,
    NOT_FOUND_TEXT,
    REFERRAL_PREFIX,
    SOURCES_HEADING,
)
from backend.llm.prompts import SYSTEM_PROMPT, PromptSource, build_user_prompt
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
    """An article shown word for word with its amendment notice and referral."""

    number: int
    citation: str
    notice: str
    text: str


@dataclass(slots=True)
class Answer:
    """Everything shown to the employee for one question."""

    text: str = ""
    amended: list[AmendedArticle] = field(default_factory=list)
    referrals: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    model_called: bool = False

    @property
    def response_type(self) -> str:
        """answer, referral or insufficient (the categories stored in query_log)."""
        if (self.text and self.text != NOT_FOUND_TEXT) or self.amended:
            return "answer"
        return "referral" if self.referrals else "insufficient"


def citation_of(candidate: Candidate) -> str:
    """Document title and article label, e.g. «نظام الأحوال المدنية، المادة 34»."""
    return f"{candidate.doc_title}، {candidate.article_label}"


def _article_text(candidate: Candidate) -> str:
    return candidate.article_text or candidate.text


def _cited_numbers(text: str, allowed: set[int]) -> tuple[str, list[int]]:
    """Remove citations to sources that do not exist; return the text and the valid ones."""
    cited: list[int] = []

    def keep_or_drop(match: re.Match[str]) -> str:
        number = int(match.group(1).translate(_ARABIC_DIGITS))
        if number not in allowed:
            return ""
        if number not in cited:
            cited.append(number)
        return f"[{number}]"

    cleaned = _CITATION.sub(keep_or_drop, text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return re.sub(r"[ \t]+([.،؛:])", r"\1", cleaned).strip(), sorted(cited)


def compose_answer(question: str, result: RetrievalResult, model: ChatModel) -> Answer:
    """Number the retrieved articles, ask the model about the plain ones, assemble the rest."""
    answer = Answer(referrals=[referral.referral_text for referral in result.referrals])
    plain: list[PromptSource] = []
    for number, candidate in enumerate(result.chunks, start=1):
        notice = result.amended_notices.get(candidate.chunk_id)
        if notice:
            answer.amended.append(
                AmendedArticle(number, citation_of(candidate), notice, _article_text(candidate))
            )
            continue
        titles = result.changed_by.get(candidate.chunk_id, [])
        note = f"(عُدّل حكم هذه المادة بموجب: {'، '.join(titles)})" if titles else ""
        plain.append(PromptSource(number, citation_of(candidate), _article_text(candidate), note))

    if plain:
        reply = model.complete(SYSTEM_PROMPT, build_user_prompt(question, plain))
        answer.model_called = True
        if NOT_FOUND_TEXT in reply:
            answer.text = NOT_FOUND_TEXT
        else:
            answer.text, cited = _cited_numbers(reply, {source.number for source in plain})
            used = [source for source in plain if source.number in cited] or plain
            answer.sources = [Source(source.number, source.citation) for source in used]
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
    for item in answer.amended:
        blocks.append(
            f"[{item.number}] {item.citation}\n{item.notice}\n"
            f"{AMENDED_TEXT_PREFIX}: «{item.text}»"
        )
    blocks += [f"{REFERRAL_PREFIX}: {text}" for text in answer.referrals]
    if answer.sources:
        lines = [f"{SOURCES_HEADING}:"]
        for source in answer.sources:
            label = f" {AMENDED_LABEL}" if source.amended else ""
            lines.append(f"[{source.number}] {source.citation}{label}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
