"""Build export rows: articles and chunks from the PDFs, reference data from data/seed/.

Only things that can be read reliably from article text are extracted here
(rule type, approval phrases, amendment markers). Decision numbers, dates,
repeal/amendment relations, issuers and procedures come from the reviewed seed
files (see seed_data.py), because OCR and keyword rules are not reliable for them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from backend.ingestion.constants import (
    APPROVAL_PHRASES,
    APPROVER_TEXT_STOP_CHARACTERS,
    ARTICLE_STATUS_AMENDED,
    ARTICLE_VERSION,
    CONDITIONAL_PROHIBITION_KEYWORDS,
    DEFAULT_EXPORT_STATUS,
    DEFAULT_RULE_TYPE,
    MANUAL_REVIEW_NOTE,
    PRIORITY_RULE_TYPES,
    PUBLIC_CLASSIFICATION_LEVEL,
    RULE_KEYWORDS,
)
from backend.ingestion.seed_data import load_seed_rows
from backend.ingestion.split import ArticleRecord, chunks_for_article

logger = logging.getLogger(__name__)
ArticleKey = tuple[str, int]
Row = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Collect rows to export for all supported knowledge tables."""

    issuers: tuple[Row, ...]
    documents: tuple[Row, ...]
    articles: tuple[Row, ...]
    chunks: tuple[Row, ...]
    document_relations: tuple[Row, ...]
    procedures: tuple[Row, ...]
    procedure_requirements: tuple[Row, ...]
    amendment_markers: tuple[Row, ...]
    roles: tuple[Row, ...] = ()
    actions: tuple[Row, ...] = ()
    employees: tuple[Row, ...] = ()
    resources: tuple[Row, ...] = ()
    decision_rules: tuple[Row, ...] = ()


def classify_rule_type(text: str) -> str:
    """Classify an article by its Arabic legal-rule keywords.

    Definitions, penalties and conditional prohibitions are checked first. For
    the remaining types the keyword that appears earliest in the text wins, so
    an article that starts with "يجوز" is a permission even if it later says
    "على أن".
    """
    for rule_type in PRIORITY_RULE_TYPES:
        if rule_type == "منع مشروط":
            if all(keyword in text for keyword in CONDITIONAL_PROHIBITION_KEYWORDS):
                return rule_type
        elif any(keyword in text for keyword in RULE_KEYWORDS[rule_type]):
            return rule_type

    first_positions = [
        (position, rule_type)
        for rule_type, keywords in RULE_KEYWORDS.items()
        if rule_type not in PRIORITY_RULE_TYPES
        for keyword in keywords
        if (position := text.find(keyword)) >= 0
    ]
    return min(first_positions)[1] if first_positions else DEFAULT_RULE_TYPE


def approval_details(text: str) -> tuple[bool, str | None]:
    """Find approval triggers and the text identifying the approver."""
    occurrences = [
        (position, phrase) for phrase in APPROVAL_PHRASES if (position := text.find(phrase)) >= 0
    ]
    if not occurrences:
        return False, None

    position, phrase = min(occurrences)
    start = position + len(phrase)
    end = next(
        (
            index
            for index in range(start, len(text))
            if text[index] in APPROVER_TEXT_STOP_CHARACTERS
        ),
        len(text),
    )
    return True, text[start:end].strip() or phrase


def _amended_article_keys(markers: tuple[dict[str, Any], ...]) -> set[ArticleKey]:
    """Return (document code, article number) for articles marked as amended."""
    return {
        (str(marker.get("document_code")), int(marker["article_no"]))
        for marker in markers
        if marker.get("document_code")
    }


def _make_article_rows(
    articles: tuple[ArticleRecord, ...],
    amended: set[ArticleKey],
    timestamp: datetime,
) -> tuple[list[Row], list[Row], dict[ArticleKey, int]]:
    """Create article and chunk rows plus a stable (code, number) -> article_id map.

    An article carrying an amendment marker keeps its (already amended) text and
    gets status "amended"; no relation is created because the amending
    instrument is not part of the source files.
    """
    rows: list[Row] = []
    chunks: list[Row] = []
    article_ids: dict[ArticleKey, int] = {}

    for article_id, article in enumerate(articles, start=1):
        key = (article.document_code, article.article_no)
        requires_approval, approver_text = approval_details(article.text)
        rows.append(
            {
                "article_id": article_id,
                "doc_id": article.doc_id,
                "article_no": article.article_no,
                "article_label": article.article_label,
                "text": article.text,
                "status": ARTICLE_STATUS_AMENDED if key in amended else DEFAULT_EXPORT_STATUS,
                "effective_from": None,
                "effective_to": None,
                "classification_level": PUBLIC_CLASSIFICATION_LEVEL,
                "rule_type": classify_rule_type(article.text),
                "requires_approval": requires_approval,
                "approver_text": approver_text,
                "version_no": ARTICLE_VERSION,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )
        article_ids[key] = article_id
        chunks.extend(chunks_for_article(article, article_id))
    return rows, chunks, article_ids


def extract_knowledge(
    articles: tuple[ArticleRecord, ...],
    source_hashes: dict[str, str],
    amendment_markers: tuple[dict[str, Any], ...],
) -> ExtractionResult:
    """Create export rows for articles and chunks, and attach the reviewed seed data."""
    timestamp = datetime.now(UTC)
    article_rows, chunks, article_ids = _make_article_rows(
        articles, _amended_article_keys(amendment_markers), timestamp
    )
    seed = load_seed_rows(article_ids, source_hashes, timestamp)

    logger.info(MANUAL_REVIEW_NOTE)
    return ExtractionResult(
        issuers=seed.issuers,
        documents=seed.documents,
        articles=tuple(article_rows),
        chunks=tuple(chunks),
        document_relations=seed.relations,
        procedures=seed.procedures,
        procedure_requirements=seed.requirements,
        amendment_markers=amendment_markers,
        roles=seed.roles,
        actions=seed.actions,
        employees=seed.employees,
        resources=seed.resources,
        decision_rules=seed.decision_rules,
    )
