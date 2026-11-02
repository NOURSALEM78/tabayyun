"""Clean extracted page text and preserve amendment markers for review."""

from __future__ import annotations

import re
import unicodedata
from typing import TypedDict

from backend.ingestion.constants import (
    AMENDMENT_MARKER_PATTERN,
    ARABIC_DIGITS,
    ARTICLE_LINE_PATTERN,
    COMMON_OCR_REPLACEMENTS,
    FORMATTING_CHARACTERS,
    HEADER_LINE,
    MAX_HEADER_LINES,
    PAGE_COUNTER_PATTERN,
    PAGE_SEPARATOR,
    REGULATION_BOUNDARY,
    STRAY_LINE_END_MARKER_PATTERN,
    WESTERN_DIGITS,
)


class AmendmentMarker(TypedDict):
    """Represent an amendment marker tied to its source article."""

    article_no: int
    marker_text: str


def convert_arabic_digits(text: str) -> str:
    """Convert Arabic-Indic digits in text to Western digits."""
    return text.translate(str.maketrans(ARABIC_DIGITS, WESTERN_DIGITS))


def _is_article_heading(line: str) -> bool:
    """Return whether a line begins an article heading."""
    return re.match(ARTICLE_LINE_PATTERN, line) is not None


def _clean_page_lines(
    page_text: str,
    header_markers: tuple[str, ...],
    preserve_markers: tuple[str, ...],
) -> list[str]:
    """Remove repeated headers and counters while retaining article headings."""
    cleaned_lines: list[str] = []
    counter_pattern = re.compile(PAGE_COUNTER_PATTERN)
    stray_marker_pattern = re.compile(STRAY_LINE_END_MARKER_PATTERN)

    for line_number, raw_line in enumerate(page_text.splitlines()):
        line = convert_arabic_digits(raw_line).replace("ـ", "")
        line = line.translate(str.maketrans("", "", FORMATTING_CHARACTERS)).strip()
        for source, replacement in COMMON_OCR_REPLACEMENTS:
            line = line.replace(source, replacement)
        line = stray_marker_pattern.sub("", line).rstrip()
        if not line or HEADER_LINE in line or counter_pattern.fullmatch(line):
            continue
        is_preserved = any(marker in line for marker in preserve_markers)
        is_title = any(marker in line for marker in header_markers)
        if line_number < MAX_HEADER_LINES and is_title and not is_preserved:
            continue
        cleaned_lines.append(line)
    return cleaned_lines


def _join_wrapped_lines(lines: list[str]) -> str:
    """Join wrapped body lines while preserving article-heading boundaries."""
    paragraphs: list[str] = []
    current: list[str] = []

    for line in lines:
        if _is_article_heading(line):
            if current:
                paragraphs.append(" ".join(current))
                current = []
            paragraphs.append(line)
        else:
            current.append(line)
    if current:
        paragraphs.append(" ".join(current))
    return "\n".join(paragraphs)


def clean_document_pages(
    pages: list[str],
    header_markers: tuple[str, ...],
    preserve_markers: tuple[str, ...] = (REGULATION_BOUNDARY,),
) -> str:
    """Clean page headers, line wrapping, Arabic digits, and whitespace."""
    cleaned_pages = [
        _join_wrapped_lines(_clean_page_lines(page, header_markers, preserve_markers))
        for page in pages
    ]
    return PAGE_SEPARATOR.join(page for page in cleaned_pages if page).strip()


def remove_amendment_markers(text: str, article_no: int) -> tuple[str, list[AmendmentMarker]]:
    """Remove amendment annotations and return their article-numbered records."""
    pattern = re.compile(AMENDMENT_MARKER_PATTERN)
    markers = [
        AmendmentMarker(article_no=article_no, marker_text=match.group("marker").strip())
        for match in pattern.finditer(text)
    ]
    cleaned_text = pattern.sub(" ", text)
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()
    return cleaned_text, markers


def collapse_whitespace(text: str) -> str:
    """Collapse whitespace without altering Arabic spelling."""
    normalized = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", normalized).strip()
