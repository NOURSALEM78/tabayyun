"""Split cleaned regulatory text into articles and searchable clauses."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from backend.ingestion.clean import (
    AmendmentMarker,
    collapse_whitespace,
    convert_arabic_digits,
    remove_amendment_markers,
)
from backend.ingestion.constants import (
    ARTICLE_PREFIX,
    CLAUSE_LETTERS,
    CLAUSE_NUMBER_START,
    FORMATTING_CHARACTERS,
    NATIONALITY_REGULATION_TITLE,
    NUMBER_MARKER_LINE_PATTERN,
    NUMERIC_HEADING_PATTERN,
    ORDINAL_COMPOUND_ONES,
    ORDINAL_HEADING_PATTERN,
    ORDINAL_ONES,
    ORDINAL_TEENS,
    ORDINAL_TEENS_MASCULINE,
    ORDINAL_TENS,
    PAGE_BREAK_CHARACTER,
    PAGE_SEPARATOR,
    PUBLIC_CLASSIFICATION_LEVEL,
    DocumentSpec,
)
from backend.ingestion.headings import heading_number_token, is_article_heading_line

logger = logging.getLogger(__name__)

ORDINAL_NUMBER_MAP: dict[str, int] = {}
for _number, _word in enumerate(ORDINAL_ONES, start=1):
    ORDINAL_NUMBER_MAP[_word] = _number
for _number, _word in enumerate(ORDINAL_TEENS, start=11):
    ORDINAL_NUMBER_MAP[_word] = _number
for _number, _word in enumerate(ORDINAL_TEENS_MASCULINE, start=11):
    ORDINAL_NUMBER_MAP[_word] = _number
for _ten_index, _word in enumerate(ORDINAL_TENS, start=2):
    _ten = _ten_index * 10
    ORDINAL_NUMBER_MAP[_word] = _ten
    for _unit, _unit_word in enumerate(ORDINAL_COMPOUND_ONES, start=1):
        ORDINAL_NUMBER_MAP[f"{_unit_word} و{_word}"] = _ten + _unit

COMPACT_ORDINAL_MAP = {
    re.sub(r"\s+", "", word): number for word, number in ORDINAL_NUMBER_MAP.items()
}
ORDINAL_HEADING_RE = re.compile(ORDINAL_HEADING_PATTERN)
NUMERIC_HEADING_RE = re.compile(NUMERIC_HEADING_PATTERN)
NUMBER_MARKER_LINE_RE = re.compile(NUMBER_MARKER_LINE_PATTERN)
CLAUSE_MARKER_RE = re.compile(
    rf"(?<!\w)(?P<letter>{'|'.join(re.escape(letter) for letter in CLAUSE_LETTERS)})"
    r"\s*(?:ـ\s*)?[-–—]\s*|(?<!\w)(?P<number>\d+)\s*[-–—]\s*"
)


@dataclass(frozen=True, slots=True)
class ArticleRecord:
    """Store a source article and its normalized document identity."""

    doc_id: int
    document_code: str
    article_no: int
    article_label: str
    text: str
    ocr_article_no: str | None = None
    page_no: int | None = None


@dataclass(frozen=True, slots=True)
class SplitResult:
    """Return split articles, removed amendment markers, and unassigned text."""

    articles: tuple[ArticleRecord, ...]
    amendment_markers: tuple[AmendmentMarker, ...]
    unassigned_text: str


@dataclass(frozen=True, slots=True)
class ClauseRecord:
    """Store a clause number and its source text."""

    clause_no: int
    text: str


def ordinal_to_number(ordinal: str) -> int | None:
    """Convert a supported Arabic ordinal word or compound to its number."""
    normalized = collapse_whitespace(ordinal).strip(" :،؛.-")
    return COMPACT_ORDINAL_MAP.get(re.sub(r"\s+", "", normalized))


def split_nationality_sections(text: str) -> tuple[str, str]:
    """Split the combined nationality PDF at its implementing-regulation title."""
    boundary_index = _find_compact_text(text, NATIONALITY_REGULATION_TITLE)
    if boundary_index < 0:
        logger.warning("Nationality regulation title was not found in the text layer")
        return text.strip(), ""
    law_text = text[:boundary_index].strip()
    regulation_text = text[boundary_index:].strip()
    return law_text, regulation_text


def _find_compact_text(text: str, target: str) -> int:
    """Find a target even when PDF extraction has removed internal spaces."""
    compact_characters: list[str] = []
    source_positions: list[int] = []
    for source_index, character in enumerate(text):
        if not character.isspace() and character != "ـ" and character not in FORMATTING_CHARACTERS:
            compact_characters.append(character)
            source_positions.append(source_index)

    compact_target = "".join(
        character
        for character in target
        if not character.isspace() and character != "ـ" and character not in FORMATTING_CHARACTERS
    )
    compact_source = "".join(compact_characters)
    match_index = compact_source.find(compact_target)
    return source_positions[match_index] if match_index >= 0 else -1


def _heading_line_spans(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, line) offsets of every article-heading line in the text."""
    spans: list[tuple[int, int, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped and is_article_heading_line(stripped):
            spans.append((offset, offset + len(line), stripped))
        offset += len(line)
    return spans


def _sequential_articles(text: str, spec: DocumentSpec) -> list[ArticleRecord]:
    """Split an OCR document at heading lines and number articles by their order.

    OCR digits inside headings are unreliable, so numbers come from the order of
    the headings. This is only safe when every heading was found: if the count
    differs from the expected count, no articles are returned and an error is
    logged, so wrongly numbered articles never reach the knowledge base.
    """
    spans = _heading_line_spans(text)
    if len(spans) != spec.expected_articles:
        logger.error(
            "%s: found %d article headings, expected %d. Numbering was not assigned; "
            "review the OCR text and the heading rules in headings.py.",
            spec.code,
            len(spans),
            spec.expected_articles,
        )
        return []

    records: list[ArticleRecord] = []
    for index, (start, end, line) in enumerate(spans):
        next_start = spans[index + 1][0] if index + 1 < len(spans) else len(text)
        number = index + 1
        records.append(
            ArticleRecord(
                doc_id=spec.doc_id,
                document_code=spec.code,
                article_no=number,
                article_label=f"{ARTICLE_PREFIX} {number}",
                text=collapse_whitespace(text[end:next_start].replace(PAGE_SEPARATOR, " ")),
                ocr_article_no=heading_number_token(line),
                page_no=text.count(PAGE_BREAK_CHARACTER, 0, start) + 1,
            )
        )
    return records


def _article_texts_by_heading(text: str, spec: DocumentSpec) -> list[ArticleRecord]:
    """Split a document whose article heading precedes each article body."""
    if spec.sequential_headings:
        return _sequential_articles(text, spec)

    heading_re = NUMERIC_HEADING_RE if spec.article_style == "numeric" else ORDINAL_HEADING_RE
    matches = list(heading_re.finditer(text))
    records: list[ArticleRecord] = []

    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw_heading_number = match.groupdict().get("number") or match.groupdict().get("ordinal")
        number = (
            int(convert_arabic_digits(raw_heading_number))
            if spec.article_style == "numeric"
            and raw_heading_number
            and convert_arabic_digits(raw_heading_number).isdigit()
            else ordinal_to_number(raw_heading_number or "")
        )
        if number is None:
            logger.warning("Could not convert article heading %r in %s", match.group(), spec.code)
            continue
        article_text = collapse_whitespace(
            text[match.end() : next_start].replace(PAGE_SEPARATOR, " ")
        )
        records.append(
            ArticleRecord(
                doc_id=spec.doc_id,
                document_code=spec.code,
                article_no=number,
                article_label=f"{ARTICLE_PREFIX} {number}",
                text=article_text,
                ocr_article_no=raw_heading_number,
                page_no=text.count(PAGE_BREAK_CHARACTER, 0, match.start()) + 1,
            )
        )
    return records


def _articles_by_number_marker_lines(text: str, spec: DocumentSpec) -> SplitResult:
    """Split the nationality law, whose number line follows each article's first line.

    pdftotext prints "-12" on its own line after the first text line of article
    12, so article n starts at the line just before marker n and ends at the
    line before the first line of article n + 1.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    anchor = next(
        (index for index, line in enumerate(lines) if spec.first_article_anchor in line), 0
    )
    markers = [
        (index, int(match.group("number")))
        for index, line in enumerate(lines)
        if index > anchor and (match := NUMBER_MARKER_LINE_RE.match(line))
    ]
    starts = [index - 1 for index, _number in markers]
    records: list[ArticleRecord] = []
    found_markers: list[AmendmentMarker] = []
    for position, (marker_index, number) in enumerate(markers):
        end = starts[position + 1] if position + 1 < len(markers) else len(lines)
        body = [lines[starts[position]], *lines[marker_index + 1 : end]]
        article_text, article_markers = remove_amendment_markers(
            collapse_whitespace(" ".join(body).replace(PAGE_BREAK_CHARACTER, " ")), number
        )
        found_markers.extend(article_markers)
        records.append(
            ArticleRecord(
                doc_id=spec.doc_id,
                document_code=spec.code,
                article_no=number,
                article_label=f"{ARTICLE_PREFIX} {number}",
                text=article_text,
                ocr_article_no=str(number),
                page_no="\n".join(lines[:marker_index]).count(PAGE_BREAK_CHARACTER) + 1,
            )
        )
    return SplitResult(tuple(records), tuple(found_markers), "")


def split_articles(text: str, spec: DocumentSpec) -> SplitResult:
    """Split one cleaned source into numbered articles and amendment records."""
    if spec.article_style == "number_suffix":
        return _articles_by_number_marker_lines(text, spec)

    records = _article_texts_by_heading(text, spec)
    markers: list[AmendmentMarker] = []
    cleaned_records: list[ArticleRecord] = []
    for article in records:
        article_text, found_markers = remove_amendment_markers(article.text, article.article_no)
        markers.extend(found_markers)
        cleaned_records.append(
            ArticleRecord(
                doc_id=article.doc_id,
                document_code=article.document_code,
                article_no=article.article_no,
                article_label=article.article_label,
                text=article_text,
                ocr_article_no=article.ocr_article_no,
                page_no=article.page_no,
            )
        )
    return SplitResult(tuple(cleaned_records), tuple(markers), "")


def split_clauses(text: str) -> list[ClauseRecord]:
    """Split article text at Arabic-letter or numbered clause markers."""
    matches = list(CLAUSE_MARKER_RE.finditer(text))
    if not matches:
        cleaned = collapse_whitespace(text)
        return [ClauseRecord(clause_no=1, text=cleaned)] if cleaned else []

    clauses: list[ClauseRecord] = []
    first_body = collapse_whitespace(text[: matches[0].start()])
    if first_body:
        clauses.append(ClauseRecord(clause_no=CLAUSE_NUMBER_START, text=first_body))

    for index, match in enumerate(matches):
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        clause_text = collapse_whitespace(text[match.end() : body_end])
        if clause_text:
            clauses.append(ClauseRecord(clause_no=len(clauses) + 1, text=clause_text))
    return clauses


def chunks_for_article(article: ArticleRecord, article_id: int) -> list[dict[str, object]]:
    """Build model-shaped chunk rows for all clauses in an article."""
    from backend.ingestion.normalize import normalize_arabic

    chunks: list[dict[str, object]] = []
    for clause in split_clauses(article.text):
        chunks.append(
            {
                "chunk_id": (
                    f"{article.document_code}-A{article.article_no:03d}-C{clause.clause_no:02d}"
                ),
                "article_id": article_id,
                "doc_id": article.doc_id,
                "clause_no": clause.clause_no,
                "text": clause.text,
                "text_normalized": normalize_arabic(clause.text),
                "embedding": None,
                "classification_level": PUBLIC_CLASSIFICATION_LEVEL,
                "is_current": True,
                "created_at": None,
            }
        )
    return chunks
