"""Validate article numbering and report text-length extremes by document."""

import logging
from collections import Counter
from typing import Any, TypedDict

from backend.ingestion.clean import convert_arabic_digits
from backend.ingestion.constants import DocumentSpec
from backend.ingestion.split import ArticleRecord, ordinal_to_number

logger = logging.getLogger(__name__)


class ValidationRow(TypedDict):
    """Represent the validation summary exported for one document."""

    document_code: str
    doc_id: int
    expected_articles: int
    actual_articles: int
    missing_numbers: list[int]
    duplicate_numbers: list[int]
    unexpected_numbers: list[int]
    heading_disagreements: list[dict[str, Any]]
    extra_heading_pages: list[dict[str, int | None]]
    missing_heading_pages: list[dict[str, int | None]]
    missing_heading_near_page: int | None
    shortest_article_no: int | None
    shortest_characters: int | None
    longest_article_no: int | None
    longest_characters: int | None
    problems: list[str]


def validate_articles(
    spec: DocumentSpec,
    articles: tuple[ArticleRecord, ...],
    page_count: int | None = None,
) -> ValidationRow:
    """Check article count and continuity, returning explicit problem details."""
    counts = Counter(article.article_no for article in articles)
    expected_numbers = set(range(1, spec.expected_articles + 1))
    actual_numbers = set(counts)
    missing_numbers = sorted(expected_numbers - actual_numbers)
    duplicate_numbers = sorted(number for number, count in counts.items() if count > 1)
    unexpected_numbers = sorted(actual_numbers - expected_numbers)
    heading_disagreements = _heading_disagreements(spec, articles)
    extra_heading_pages = [
        {"article_no": article.article_no, "page_no": article.page_no}
        for article in articles[spec.expected_articles :]
    ]
    missing_heading_near_page = (
        page_count or (articles[-1].page_no if articles else None)
        if len(articles) < spec.expected_articles
        else None
    )
    missing_heading_pages = [
        {"article_no": article_no, "near_page": missing_heading_near_page}
        for article_no in missing_numbers
    ]
    shortest = min(articles, key=lambda article: len(article.text), default=None)
    longest = max(articles, key=lambda article: len(article.text), default=None)
    problems: list[str] = []

    if len(articles) != spec.expected_articles:
        problems.append(f"Expected {spec.expected_articles} articles; extracted {len(articles)}.")
    if missing_numbers:
        problems.append(f"Missing article numbers: {missing_numbers}.")
    if duplicate_numbers:
        problems.append(f"Duplicated article numbers: {duplicate_numbers}.")
    if unexpected_numbers:
        problems.append(f"Unexpected article numbers: {unexpected_numbers}.")
    if extra_heading_pages:
        problems.append(f"Extra headings occur near pages: {extra_heading_pages}.")
    if missing_heading_near_page is not None and len(articles) < spec.expected_articles:
        problems.append(
            f"Missing headings continue through the end of the source near page "
            f"{missing_heading_near_page}."
        )

    if spec.sequential_headings and len(articles) != spec.expected_articles:
        problems.append(
            f"Expected {spec.expected_articles} article headings; detected {len(articles)}."
        )

    return ValidationRow(
        document_code=spec.code,
        doc_id=spec.doc_id,
        expected_articles=spec.expected_articles,
        actual_articles=len(articles),
        missing_numbers=missing_numbers,
        duplicate_numbers=duplicate_numbers,
        unexpected_numbers=unexpected_numbers,
        heading_disagreements=heading_disagreements,
        extra_heading_pages=extra_heading_pages,
        missing_heading_pages=missing_heading_pages,
        missing_heading_near_page=missing_heading_near_page,
        shortest_article_no=shortest.article_no if shortest else None,
        shortest_characters=len(shortest.text) if shortest else None,
        longest_article_no=longest.article_no if longest else None,
        longest_characters=len(longest.text) if longest else None,
        problems=problems,
    )


def _heading_disagreements(
    spec: DocumentSpec, articles: tuple[ArticleRecord, ...]
) -> list[dict[str, Any]]:
    """List sequential article headings whose OCR token disagrees with assigned order."""
    if not spec.sequential_headings:
        return []

    disagreements: list[dict[str, Any]] = []
    for article in articles:
        raw_number = article.ocr_article_no or ""
        normalized_number = convert_arabic_digits(raw_number).strip()
        try:
            read_number = int(normalized_number)
        except ValueError:
            read_number = ordinal_to_number(raw_number)
        if read_number == article.article_no:
            continue
        disagreements.append(
            {
                "article_no": article.article_no,
                "ocr_heading_number": raw_number,
                "page_no": article.page_no,
            }
        )
    return disagreements


def log_validation(row: ValidationRow) -> None:
    """Log one document's validation details without hiding numbering issues."""
    logger.info(
        "%s article lengths: shortest=%s/%s chars; longest=%s/%s chars",
        row["document_code"],
        row["shortest_article_no"],
        row["shortest_characters"],
        row["longest_article_no"],
        row["longest_characters"],
    )
    if row["problems"]:
        logger.warning(
            "%s validation problems: %s", row["document_code"], " ".join(row["problems"])
        )
    else:
        logger.info(
            "%s validation passed: %d articles",
            row["document_code"],
            row["actual_articles"],
        )
