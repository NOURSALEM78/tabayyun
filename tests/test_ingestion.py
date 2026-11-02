"""Tests for Arabic document cleaning, splitting, classification, and caching."""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

import pytest
from openpyxl import load_workbook
from PIL import Image

from backend.ingestion.clean import (
    clean_document_pages,
    collapse_whitespace,
    convert_arabic_digits,
    remove_amendment_markers,
)
from backend.ingestion.constants import DOCUMENT_SPECS, PAGE_SEPARATOR, DocumentSpec
from backend.ingestion.export import write_workbook
from backend.ingestion.extract import (
    DECISION_NUMBER_RE,
    ExtractionResult,
    approval_details,
    classify_rule_type,
)
from backend.ingestion.headings import is_article_heading_line
from backend.ingestion.normalize import normalize_arabic
from backend.ingestion.ocr import read_pdf_pages
from backend.ingestion.split import (
    ArticleRecord,
    chunks_for_article,
    ordinal_to_number,
    split_articles,
    split_clauses,
    split_nationality_sections,
)
from backend.ingestion.validate import log_validation, validate_articles


def test_convert_arabic_digits() -> None:
    """Convert article and date digits without changing Arabic letters."""
    assert convert_arabic_digits("المادة ٩٦ بتاريخ ١٤٤٣") == "المادة 96 بتاريخ 1443"


def test_clean_document_pages_applies_common_ocr_fixes() -> None:
    """Normalize the specified OCR punctuation and strip isolated line-end markers."""
    cleaned = clean_document_pages(["نص » معاملة ٧"], (), ())

    assert cleaned == "نص ، معاملة"


def test_clean_document_pages_removes_headers_and_preserves_body() -> None:
    """Remove repeated headers/counters while retaining Arabic article text."""
    pages = [
        "الإدارة القانونية\nنظام الأحوال المدنية\n١ من ٢٧\nالمادة الأولى\nنص الأحوال المدنيةـ",
        "الإدارة القانونية\nنظام الأحوال المدنية\n٢ من ٢٧\nالمادة الثانية\nنص مستمر",
    ]

    cleaned = clean_document_pages(pages, DOCUMENT_SPECS[0].header_markers, ())

    assert "الإدارة القانونية" not in cleaned
    assert "نظام الأحوال المدنية" not in cleaned
    assert "المادة الأولى" in cleaned
    assert "المادة الثانية" in cleaned
    assert "نص الأحوال المدنية" in cleaned
    assert "ـ" not in cleaned


def test_remove_amendment_markers_returns_records() -> None:
    """Remove both textual and numbered amendment markers for review."""
    cleaned, markers = remove_amendment_markers(
        "نص المادة *تعديلات المادة الثانية وبند * (1) يستمر", 2
    )

    assert "تعديلات المادة" not in cleaned
    assert "(1)" not in cleaned
    assert markers == [
        {"article_no": 2, "marker_text": "تعديلات المادة الثانية وبند"},
        {"article_no": 2, "marker_text": "(1)"},
    ]


def test_collapse_whitespace_preserves_original_arabic_spelling() -> None:
    """Collapse page wrapping without normalizing hamza or ta marbuta."""
    assert collapse_whitespace("الأحوال\n المدنية  ") == "الأحوال المدنية"


def test_normalize_arabic_is_search_only() -> None:
    """Remove marks and punctuation and unify Arabic search letter forms."""
    assert normalize_arabic("أَإِآ، ة ى؟") == "ااا ه ي"


@pytest.mark.parametrize(
    ("ordinal", "expected"),
    (("الأولى", 1), ("العاشرة", 10), ("الحادية والعشرون", 21), ("التاسعة والتسعون", 99)),
)
def test_ordinal_to_number(ordinal: str, expected: int) -> None:
    """Convert Arabic ordinal words to their article numbers."""
    assert ordinal_to_number(ordinal) == expected


def test_split_ordinal_articles_and_markers() -> None:
    """Split ordinal article headings and retain markers outside article text."""
    source = "المادة الأولى\nنص أول\nالمادة الحادية والعشرون\n* (1) نص حادي وعشرون"

    result = split_articles(source, _with_expected(DOCUMENT_SPECS[0], 2))

    assert result.articles[1].text == "نص حادي وعشرون"
    assert [article.article_no for article in result.articles] == [1, 2]
    assert result.articles[1].ocr_article_no == "الحادية والعشرون"
    assert result.amendment_markers == ({"article_no": 2, "marker_text": "(1)"},)


def test_split_numeric_articles() -> None:
    """Split numeric article headings used by the civil-status regulation."""
    result = split_articles(
        "المادة (1)\nالأولى\nالمادة (2)\nالثانية", _with_expected(DOCUMENT_SPECS[1], 2)
    )

    assert [(article.article_no, article.text) for article in result.articles] == [
        (1, "الأولى"),
        (2, "الثانية"),
    ]


def test_sequential_heading_numbers_ignore_ocr_digits_and_keep_pages() -> None:
    """Assign sequential IDs despite wrong OCR digits and retain page locations."""
    source = f"المادة (٦)\nنص أول{PAGE_SEPARATOR}المادة (/1)\nنص ثان"

    result = split_articles(source, _with_expected(DOCUMENT_SPECS[1], 2))

    assert [article.article_no for article in result.articles] == [1, 2]
    assert [article.ocr_article_no for article in result.articles] == ["(٦)", "(/1)"]
    assert [article.page_no for article in result.articles] == [1, 2]
    report = validate_articles(DOCUMENT_SPECS[1], result.articles, page_count=2)
    assert report["heading_disagreements"] == [
        {"article_no": 1, "ocr_heading_number": "(٦)", "page_no": 1},
        {"article_no": 2, "ocr_heading_number": "(/1)", "page_no": 2},
    ]


def test_split_nationality_law_trailing_numbers() -> None:
    """Decode RTL trailing article numbers in the nationality law."""
    source = "يسمى هذا النظام نظام الجنسية-١\nلا يجوز إلا بإذن-٢\n"

    result = split_articles(source, DOCUMENT_SPECS[2])

    assert [article.article_no for article in result.articles] == [1, 2]
    assert result.articles[0].text.startswith("يسمى هذا النظام")
    assert result.unassigned_text == ""


def test_split_combined_nationality_sections() -> None:
    """Split the combined PDF even when text extraction removes title spaces."""
    law, regulation = split_nationality_sections(
        "المادةالثلاثون نص\nاللائحةالتنفيذيةلنظامالجنسيةالعربيةالسعودية\nالمادةالأولى نص"
    )

    assert "المادةالثلاثون" in law
    assert "اللائحةالتنفيذية" in regulation


def test_split_clauses_and_build_chunk_ids() -> None:
    """Split Arabic lettered clauses and produce stable normalized chunk IDs."""
    article = ArticleRecord(1, "CSL", 11, "المادة 11", "أ - إرفاق صورة ب- مراجعة الإدارة")
    clauses = split_clauses(article.text)
    chunks = chunks_for_article(article, 1)

    assert [clause.text for clause in clauses] == ["إرفاق صورة", "مراجعة الإدارة"]
    assert [chunk["chunk_id"] for chunk in chunks] == ["CSL-A011-C01", "CSL-A011-C02"]
    assert chunks[0]["text_normalized"] == "ارفاق صوره"


def test_rule_type_and_approval_details() -> None:
    """Classify common legal rules and extract their approving authority."""
    assert classify_rule_type("لا يجوز ذلك إلا بقرار من الوزير") == "منع مشروط"
    assert classify_rule_type("يعاقب بغرامة") == "عقوبة"
    assert approval_details("يجوز بقرار من وزير الداخلية، بعد تقديم الطلب") == (
        True,
        "وزير الداخلية",
    )
    assert approval_details("يسجل الطلب") == (False, None)


def test_decision_number_regex_rejects_partial_ocr_tokens() -> None:
    """Reject IDs that only partially match before OCR-confused Arabic letters."""
    source = "القرار الوزاري رقم (960ا/ون)، والقرار الوزاري رقم (9)"

    assert [match.group("number") for match in DECISION_NUMBER_RE.finditer(source)] == ["9"]


def test_validation_reports_missing_and_duplicate_numbers() -> None:
    """Report missing and duplicated article numbers instead of skipping them."""
    first = ArticleRecord(1, "CSL", 1, "المادة 1", "نص أول")
    duplicate = ArticleRecord(1, "CSL", 1, "المادة 1", "نص مكرر")
    out_of_range = ArticleRecord(1, "CSL", 97, "المادة 97", "نص خارج النطاق")

    report = validate_articles(DOCUMENT_SPECS[0], (first, duplicate, out_of_range), page_count=27)

    assert report["duplicate_numbers"] == [1]
    assert report["missing_numbers"] == list(range(2, 97))
    assert report["unexpected_numbers"] == [97]
    assert report["missing_heading_pages"][0] == {"article_no": 2, "near_page": 27}
    assert report["shortest_characters"] == len("نص أول")
    assert report["longest_characters"] == len("نص خارج النطاق")


def test_validation_logs_lengths_when_article_numbers_fail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Include shortest/longest article lengths alongside numbering problems."""
    row = validate_articles(DOCUMENT_SPECS[0], ())

    with caplog.at_level(logging.INFO):
        log_validation(row)

    assert "shortest=None/None chars; longest=None/None chars" in caplog.text
    assert "Expected 96 articles; extracted 0." in caplog.text


def test_export_converts_timezone_aware_datetimes(tmp_path: Path) -> None:
    """Write timezone-aware extraction timestamps as UTC-naive Excel datetimes."""
    extraction = ExtractionResult(
        issuers=(),
        documents=({"doc_id": 1, "created_at": datetime(2026, 1, 1, tzinfo=UTC)},),
        articles=(),
        chunks=(),
        document_relations=(),
        procedures=({"procedure_id": 1, "aliases": ["إجراء"]},),
        procedure_requirements=(),
        amendment_markers=(),
    )
    workbook_path = write_workbook(extraction, (), tmp_path / "knowledge.xlsx")
    workbook = load_workbook(workbook_path, read_only=True)
    value = workbook["documents"]["O2"].value
    aliases = workbook["procedures"]["C2"].value
    workbook.close()

    assert isinstance(value, datetime)
    assert value.tzinfo is None
    assert aliases == '["إجراء"]'


class _FakePage:
    """Supply one stable text-layer page for the cache idempotency test."""

    def get_text(self, text_type: str, sort: bool = False) -> str:
        """Return the page text expected by the PyMuPDF adapter."""
        del text_type, sort
        return "المادة الأولى"


class _FakeDocument:
    """Act as a minimal context-managed PDF document."""

    def __init__(self) -> None:
        self.page = _FakePage()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def __len__(self) -> int:
        return 1

    def __iter__(self) -> Iterator[_FakePage]:
        yield self.page


def test_read_pdf_pages_reuses_cached_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Read and reuse page text from cache without reopening OCR on later runs."""
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"not parsed because page cache is already present")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "page_001.txt").write_text("المادة الأولى", encoding="utf-8")
    monkeypatch.setattr("backend.ingestion.ocr.pymupdf.open", lambda _path: _FakeDocument())

    assert read_pdf_pages(source_path, cache_dir, text_layer=True) == ["المادة الأولى"]


def test_scanned_pages_use_poppler_and_report_white_or_short_ocr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Render grayscale via Poppler and report suspect page images/OCR output."""
    source_path = tmp_path / "scanned.pdf"
    source_path.write_bytes(b"mock PDF")
    render_calls: list[dict[str, object]] = []

    def fake_convert_from_path(path: str, **kwargs: object) -> list[Image.Image]:
        render_calls.append({"path": path, **kwargs})
        return [Image.new("L", (10, 10), color=255)]

    monkeypatch.setattr("backend.ingestion.ocr.pymupdf.open", lambda _path: _FakeDocument())
    monkeypatch.setattr("backend.ingestion.ocr.convert_from_path", fake_convert_from_path)
    monkeypatch.setattr(
        "backend.ingestion.ocr.pytesseract.image_to_string", lambda *_args, **_kwargs: "نص"
    )

    with caplog.at_level(logging.ERROR):
        pages = read_pdf_pages(source_path, tmp_path / "ocr-cache")

    assert pages == ["نص"]
    assert render_calls[0]["dpi"] == 300
    assert render_calls[0]["grayscale"] is True
    assert "no visible ink" in caplog.text
    assert "fewer than 50 characters" in caplog.text
    assert "page 1" in caplog.text


def _with_expected(spec: DocumentSpec, expected: int) -> DocumentSpec:
    """Return a copy of a document spec with a small expected article count for tests."""
    return dataclasses.replace(spec, expected_articles=expected)


@pytest.mark.parametrize(
    "line",
    [
        "المادة (٤٠)",
        "المادة )١77/(\u200f",  # OCR digits garbled, bidi mark kept
        ")١5( المادة\u200e",  # line reversed by OCR
        "المادة ١ )١4(",
        "المادة",  # number not read at all
        "المادة/ الأولى",
        "المادة/ الثامنة والثمانون",  # contains the letters of "من" inside a word
    ],
)
def test_heading_lines_are_recognised(line: str) -> None:
    """Recognise article headings even when OCR garbles or reverses them."""
    assert is_article_heading_line(line)


@pytest.mark.parametrize(
    "line",
    [
        "المادة (15) من النظام.",  # in-text reference
        "المادة )١١( من هذه اللائحة.",
        "الخاصة والحالات الأخرى غير الواردة في هذه المادة.",
        "*تعديلات المادة الثانية",  # amendment marker
        "المادة. ا",  # sentence ending with the word
        "يتم تسجيل الواقعة وفق ما ورد في المادة (25) من هذه اللائحة",
    ],
)
def test_non_heading_lines_are_rejected(line: str) -> None:
    """Reject in-text references, amendment markers, and sentence endings."""
    assert not is_article_heading_line(line)


def test_sequential_split_refuses_wrong_heading_count(caplog: pytest.LogCaptureFixture) -> None:
    """Return no articles when the heading count differs, so numbers are never shifted."""
    source = "المادة (١)\nنص أول\nالمادة (٢)\nنص ثان"

    with caplog.at_level(logging.ERROR):
        result = split_articles(source, _with_expected(DOCUMENT_SPECS[1], 3))

    assert result.articles == ()
    assert "found 2 article headings, expected 3" in caplog.text


def test_blank_page_check_accepts_normal_text_pages(tmp_path: Path) -> None:
    """A mostly white page with some ink is not blank; an all-white page is."""
    from backend.ingestion.ocr import _is_blank

    page = Image.new("L", (100, 100), color=255)
    assert _is_blank(page)
    for x in range(100):
        for y in range(0, 100, 10):
            page.putpixel((x, y), 0)
    assert not _is_blank(page)
