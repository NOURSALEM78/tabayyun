"""Extract reviewable legal rules, authorities, relations, and draft procedures."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from backend.ingestion.constants import (
    APPROVAL_PHRASES,
    APPROVER_TEXT_STOP_CHARACTERS,
    ARTICLE_VERSION,
    CONDITIONAL_PROHIBITION_KEYWORDS,
    DECISION_CONTEXT_CHARACTERS,
    DECISION_NUMBER_PATTERN,
    DEFAULT_ARTICLE_DATE,
    DEFAULT_DOCUMENT_NUMBER,
    DEFAULT_EXPORT_STATUS,
    DEFAULT_ISSUER_REFERRAL,
    DEFAULT_RESPONSIBLE_DEPARTMENT,
    DEFAULT_SOURCE_URL,
    DOCUMENT_CODE_CIVIL_REGULATION,
    DOCUMENT_SPECS,
    DOCUMENT_STATUS_ACTIVE,
    DOCUMENT_STATUS_REPEALED,
    ISSUER_NAMES,
    ISSUER_TYPE_EXECUTIVE,
    ISSUER_TYPE_INTERNAL,
    LEGACY_NATIONALITY_ARTICLE_NO,
    LEGACY_NATIONALITY_LAW_TITLE,
    MANUAL_REVIEW_NOTE,
    NATIONALITY_TEXT_CODE,
    PROCEDURE_MANDATORY_KEYWORDS,
    PROCEDURE_NAME_MAX_LENGTH,
    PROCEDURE_REVIEW_DRAFT,
    PROCEDURE_START_PHRASES,
    PUBLIC_CLASSIFICATION_LEVEL,
    REFERENCED_LEGAL_TITLES,
    REGULATION_DOCUMENT_ID,
    RELATION_AMENDS,
    RELATION_REPEALS,
    RELATION_REPLACES,
    REQUIREMENT_KEYWORDS,
    REQUIREMENT_STATEMENT_TYPE,
    RULE_KEYWORDS,
    DocumentSpec,
)
from backend.ingestion.split import ArticleRecord, chunks_for_article, split_clauses

logger = logging.getLogger(__name__)
DECISION_NUMBER_RE = re.compile(DECISION_NUMBER_PATTERN)
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


def classify_rule_type(text: str) -> str:
    """Classify an article using the specified Arabic legal-rule keywords."""
    for rule_type, keywords in RULE_KEYWORDS.items():
        if rule_type == "منع مشروط":
            if all(keyword in text for keyword in CONDITIONAL_PROHIBITION_KEYWORDS):
                return rule_type
        elif any(keyword in text for keyword in keywords):
            return rule_type
    return "إجرائي"


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


def _find_issuers(source_texts: tuple[str, ...]) -> list[Row]:
    """Create issuer rows only for authority names occurring in source text."""
    combined_text = "\n".join(source_texts)
    found_names = [name for name in ISSUER_NAMES if name in combined_text]
    return [
        {
            "issuer_id": issuer_id,
            "name": name,
            "issuer_type": ISSUER_TYPE_INTERNAL if "اللجنة" in name else ISSUER_TYPE_EXECUTIVE,
            "referral_text": DEFAULT_ISSUER_REFERRAL,
        }
        for issuer_id, name in enumerate(found_names, start=1)
    ]


def _source_document_row(
    spec: DocumentSpec,
    issuer_id: int | None,
    source_hash: str,
    timestamp: datetime,
) -> Row:
    """Build a documents row for a supplied source PDF."""
    return {
        "doc_id": spec.doc_id,
        "doc_type": spec.doc_type,
        "title": spec.title,
        "doc_number": DEFAULT_DOCUMENT_NUMBER,
        "issuer_id": issuer_id,
        "issue_date_hijri": DEFAULT_ARTICLE_DATE,
        "issue_date": None,
        "effective_from": None,
        "effective_to": None,
        "status": DEFAULT_EXPORT_STATUS,
        "classification_level": PUBLIC_CLASSIFICATION_LEVEL,
        "source_url": DEFAULT_SOURCE_URL,
        "file_path": f"data/raw/{spec.source_filename}",
        "content_hash": source_hash,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _reference_document_row(
    doc_id: int,
    title: str,
    doc_number: str,
    status: str,
    issuer_id: int | None,
    timestamp: datetime,
) -> Row:
    """Build a documents row for a legal reference found in source text."""
    return {
        "doc_id": doc_id,
        "doc_type": "decision" if doc_number else "law",
        "title": title,
        "doc_number": doc_number,
        "issuer_id": issuer_id,
        "issue_date_hijri": DEFAULT_ARTICLE_DATE,
        "issue_date": None,
        "effective_from": None,
        "effective_to": None,
        "status": status,
        "classification_level": PUBLIC_CLASSIFICATION_LEVEL,
        "source_url": DEFAULT_SOURCE_URL,
        "file_path": DEFAULT_SOURCE_URL,
        "content_hash": DEFAULT_SOURCE_URL,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _relation_row(
    relation_id: int,
    source_doc_id: int,
    target_doc_id: int,
    relation_type: str,
    notes: str,
    source_article_id: int | None = None,
) -> Row:
    """Build a document_relations row with text evidence from its source."""
    return {
        "relation_id": relation_id,
        "source_doc_id": source_doc_id,
        "source_article_id": source_article_id,
        "target_doc_id": target_doc_id,
        "target_article_id": None,
        "relation_type": relation_type,
        "effective_from": None,
        "notes": notes,
    }


def _decision_relation_kind(context: str) -> tuple[str, str] | None:
    """Identify a replacement or amendment described in a decision context."""
    if "الملغاة باللائحة" in context or "ملغاة باللائحة" in context:
        return RELATION_REPLACES, DOCUMENT_STATUS_REPEALED
    if "تعديل" in context or "عدلت" in context:
        return RELATION_AMENDS, DOCUMENT_STATUS_ACTIVE
    return None


def _extract_decision_relations(
    regulation_text: str,
    issuer_id: int | None,
    timestamp: datetime,
    next_doc_id: int,
    next_relation_id: int,
) -> tuple[list[Row], list[Row]]:
    """Create rows for decision numbers explicitly described as amending/replacing."""
    documents: list[Row] = []
    relations: list[Row] = []
    seen_numbers: set[str] = set()

    for match in DECISION_NUMBER_RE.finditer(regulation_text):
        doc_number = re.sub(r"\s+", "", match.group("number"))
        if doc_number in seen_numbers:
            continue
        context_start = max(0, match.start() - DECISION_CONTEXT_CHARACTERS)
        context_end = min(len(regulation_text), match.end() + DECISION_CONTEXT_CHARACTERS)
        context = regulation_text[context_start:context_end]
        relation_details = _decision_relation_kind(context)
        if relation_details is None:
            continue
        relation_type, status = relation_details
        reference_id = next_doc_id + len(documents)
        documents.append(
            _reference_document_row(
                reference_id,
                f"قرار وزاري رقم {doc_number}",
                doc_number,
                status,
                issuer_id,
                timestamp,
            )
        )
        source_id = reference_id if relation_type == RELATION_AMENDS else REGULATION_DOCUMENT_ID
        target_id = REGULATION_DOCUMENT_ID if relation_type == RELATION_AMENDS else reference_id
        relations.append(
            _relation_row(
                next_relation_id + len(relations),
                source_id,
                target_id,
                relation_type,
                context.strip(),
            )
        )
        seen_numbers.add(doc_number)
    return documents, relations


def _article_id(article: ArticleRecord, source_ids: dict[ArticleKey, int]) -> int:
    """Return the assigned database-style ID for a source article."""
    return source_ids[(article.document_code, article.article_no)]


def _extract_named_references(
    source_texts: dict[str, str],
    articles: tuple[ArticleRecord, ...],
    source_ids: dict[ArticleKey, int],
    timestamp: datetime,
    next_doc_id: int,
    next_relation_id: int,
    issuer_id: int | None,
) -> tuple[list[Row], list[Row]]:
    """Create repeal references only when their legal titles occur in article text."""
    documents: list[Row] = []
    relations: list[Row] = []
    combined_text = "\n".join(source_texts.values())

    for title, status in REFERENCED_LEGAL_TITLES:
        if title not in combined_text:
            continue
        source_code = next(
            (code for code, text in source_texts.items() if title in text),
            None,
        )
        source_spec = next(
            (spec for spec in DOCUMENT_SPECS if spec.code == source_code),
            None,
        )
        if source_spec is None:
            logger.warning("Referenced title %r has no resolved source document", title)
            continue
        source_article = next(
            (
                article
                for article in articles
                if article.document_code == source_code and title in article.text
            ),
            None,
        )
        reference_id = next_doc_id + len(documents)
        documents.append(
            _reference_document_row(
                reference_id, title, DEFAULT_DOCUMENT_NUMBER, status, issuer_id, timestamp
            )
        )
        relations.append(
            _relation_row(
                next_relation_id + len(relations),
                source_spec.doc_id,
                reference_id,
                RELATION_REPEALS,
                f"Source text mentions: {title}",
                _article_id(source_article, source_ids) if source_article else None,
            )
        )
    return documents, relations


def _extract_nationality_repeal(
    articles: tuple[ArticleRecord, ...],
    source_ids: dict[ArticleKey, int],
    issuer_id: int | None,
    timestamp: datetime,
    doc_id: int,
    relation_id: int,
) -> tuple[Row, Row] | None:
    """Create the legacy nationality-law repeal rows when article 28 states them."""
    source_article = next(
        (
            article
            for article in articles
            if article.document_code == NATIONALITY_TEXT_CODE
            and article.article_no == LEGACY_NATIONALITY_ARTICLE_NO
            and "يلغى" in re.sub(r"\s+", "", article.text)
            and "نظامالجنسيةالعربيةالسعودية" in re.sub(r"\s+", "", article.text)
        ),
        None,
    )
    if source_article is None:
        return None
    document = _reference_document_row(
        doc_id,
        LEGACY_NATIONALITY_LAW_TITLE,
        DEFAULT_DOCUMENT_NUMBER,
        DOCUMENT_STATUS_REPEALED,
        issuer_id,
        timestamp,
    )
    relation = _relation_row(
        relation_id,
        source_article.doc_id,
        doc_id,
        RELATION_REPEALS,
        source_article.text,
        _article_id(source_article, source_ids),
    )
    return document, relation


def _make_article_rows(
    articles: tuple[ArticleRecord, ...], timestamp: datetime
) -> tuple[list[Row], list[Row], dict[ArticleKey, int]]:
    """Create article and chunk rows plus a stable source-to-ID mapping."""
    rows: list[Row] = []
    chunks: list[Row] = []
    source_ids: dict[ArticleKey, int] = {}

    for article_id, article in enumerate(articles, start=1):
        requires_approval, approver_text = approval_details(article.text)
        rows.append(
            {
                "article_id": article_id,
                "doc_id": article.doc_id,
                "article_no": article.article_no,
                "article_label": article.article_label,
                "text": article.text,
                "status": DEFAULT_EXPORT_STATUS,
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
        source_ids[(article.document_code, article.article_no)] = article_id
        chunks.extend(chunks_for_article(article, article_id))
    return rows, chunks, source_ids


def _amendment_relations(
    markers: tuple[Row, ...], source_ids: dict[ArticleKey, int], next_relation_id: int
) -> list[Row]:
    """Record amendment markers as unresolved, source-linked review relations."""
    relations: list[Row] = []
    specs_by_code = {spec.code: spec for spec in DOCUMENT_SPECS}
    for marker in markers:
        document_code = marker.get("document_code")
        article_no = marker["article_no"]
        spec = specs_by_code.get(document_code)
        article_id = source_ids.get((document_code, article_no))
        if spec is None or article_id is None:
            logger.warning(
                "Amendment marker has no article mapping: %s/%s",
                document_code,
                article_no,
            )
            continue
        relations.append(
            _relation_row(
                next_relation_id + len(relations),
                spec.doc_id,
                spec.doc_id,
                RELATION_AMENDS,
                f"Unresolved amendment marker; manual review required: {marker['marker_text']}",
                article_id,
            )
        )
    return relations


def _requirement_type(text: str) -> str:
    """Guess a requirement category from the source clause's Arabic keywords."""
    for requirement_type, keywords in REQUIREMENT_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return requirement_type
    return REQUIREMENT_STATEMENT_TYPE


def _procedure_row(
    article: ArticleRecord,
    procedure_id: int,
    article_id: int,
    timestamp: datetime,
) -> Row:
    """Build a draft procedure row sourced from one article."""
    return {
        "procedure_id": procedure_id,
        "name": article.text[:PROCEDURE_NAME_MAX_LENGTH].strip(),
        "aliases": [],
        "description": article.text,
        "responsible_department": DEFAULT_RESPONSIBLE_DEPARTMENT,
        "source_doc_id": article.doc_id,
        "source_article_id": article_id,
        "status": PROCEDURE_REVIEW_DRAFT,
        "review_status": PROCEDURE_REVIEW_DRAFT,
        "updated_at": timestamp,
    }


def _procedure_requirements(
    article: ArticleRecord,
    procedure_id: int,
    article_id: int,
    first_requirement_id: int,
) -> list[Row]:
    """Build one source-linked requirement row for each clause in an article."""
    requirements: list[Row] = []
    for order_no, clause in enumerate(split_clauses(article.text), start=1):
        requirements.append(
            {
                "requirement_id": first_requirement_id + order_no - 1,
                "procedure_id": procedure_id,
                "requirement_type": _requirement_type(clause.text),
                "name": clause.text[:PROCEDURE_NAME_MAX_LENGTH],
                "description": clause.text,
                "is_mandatory": any(
                    keyword in clause.text for keyword in PROCEDURE_MANDATORY_KEYWORDS
                ),
                "source_article_id": article_id,
                "order_no": order_no,
            }
        )
    return requirements


def _make_procedure_rows(
    articles: tuple[ArticleRecord, ...],
    source_ids: dict[ArticleKey, int],
    timestamp: datetime,
) -> tuple[list[Row], list[Row]]:
    """Create draft procedures for articles that appear to describe requests."""
    procedures: list[Row] = []
    requirements: list[Row] = []
    for article in articles:
        if not any(phrase in article.text for phrase in PROCEDURE_START_PHRASES):
            continue
        procedure_id = len(procedures) + 1
        article_id = _article_id(article, source_ids)
        procedures.append(_procedure_row(article, procedure_id, article_id, timestamp))
        requirements.extend(
            _procedure_requirements(article, procedure_id, article_id, len(requirements) + 1)
        )
    return procedures, requirements


def _source_documents(
    source_hashes: dict[str, str], issuer_id: int | None, timestamp: datetime
) -> list[Row]:
    """Create the base document rows for every logical source document."""
    return [
        _source_document_row(
            spec,
            issuer_id,
            source_hashes.get(spec.source_filename, DEFAULT_SOURCE_URL),
            timestamp,
        )
        for spec in DOCUMENT_SPECS
    ]


def extract_knowledge(
    articles: tuple[ArticleRecord, ...],
    source_texts: dict[str, str],
    source_hashes: dict[str, str],
    amendment_markers: tuple[dict[str, Any], ...],
) -> ExtractionResult:
    """Create export rows for sources, articles, clauses, and review candidates."""
    timestamp = datetime.now(UTC)
    issuer_rows = _find_issuers(tuple(source_texts.values()))
    issuer_id = issuer_rows[0]["issuer_id"] if issuer_rows else None
    documents = _source_documents(source_hashes, issuer_id, timestamp)
    article_rows, chunks, source_ids = _make_article_rows(articles, timestamp)
    procedures, requirements = _make_procedure_rows(articles, source_ids, timestamp)
    decision_docs, decision_relations = _extract_decision_relations(
        source_texts.get(DOCUMENT_CODE_CIVIL_REGULATION, ""),
        issuer_id,
        timestamp,
        max(row["doc_id"] for row in documents) + 1,
        1,
    )
    named_docs, named_relations = _extract_named_references(
        source_texts,
        articles,
        source_ids,
        timestamp,
        max(row["doc_id"] for row in documents + decision_docs) + 1,
        len(decision_relations) + 1,
        issuer_id,
    )
    documents.extend(decision_docs + named_docs)
    relations = decision_relations + named_relations
    repeal_result = _extract_nationality_repeal(
        articles,
        source_ids,
        issuer_id,
        timestamp,
        max(row["doc_id"] for row in documents) + 1,
        len(relations) + 1,
    )
    if repeal_result is not None:
        reference_document, repeal_relation = repeal_result
        documents.append(reference_document)
        relations.append(repeal_relation)
    relations.extend(_amendment_relations(amendment_markers, source_ids, len(relations) + 1))

    logger.info(MANUAL_REVIEW_NOTE)
    return ExtractionResult(
        issuers=tuple(issuer_rows),
        documents=tuple(documents),
        articles=tuple(article_rows),
        chunks=tuple(chunks),
        document_relations=tuple(relations),
        procedures=tuple(procedures),
        procedure_requirements=tuple(requirements),
        amendment_markers=amendment_markers,
    )
