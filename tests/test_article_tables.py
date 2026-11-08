"""Tests for reading reviewed article tables from data/raw/."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from openpyxl import Workbook

from backend.ingestion.article_tables import ArticleTableError, read_article_table
from backend.ingestion.constants import (
    DOCUMENT_SPECS,
    REVIEW_COL_ARTICLE,
    REVIEW_COL_CODE,
    REVIEW_COL_PAGE,
    REVIEW_COL_TEXT,
    TABLE_DOCUMENT_SPECS,
)

SPEC = dataclasses.replace(DOCUMENT_SPECS[0], table_filename="test_articles.xlsx")
HEADER = ("النظام", REVIEW_COL_CODE, REVIEW_COL_ARTICLE, REVIEW_COL_PAGE, REVIEW_COL_TEXT)


def _write_table(directory: Path, rows: list[tuple[object, ...]], header=HEADER) -> None:
    """Write a one-sheet article table like the team's files."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    workbook.save(directory / SPEC.table_filename)


def test_reads_rows_sorted_with_digits_and_whitespace_normalized(tmp_path: Path) -> None:
    """Rows become articles sorted by number; Arabic digits and line breaks are normalized."""
    _write_table(
        tmp_path,
        [
            ("نظام", "CSL", 2, 3, "وفقا للمادة (٨٦)\nمن هذا النظام."),
            ("نظام", "CSL", "١", "2", "أ- ضبط الحالة.\nب- تدوين الواقعات."),
            (None, None, None, None, None),  # blank rows are ignored
        ],
    )

    articles = read_article_table(SPEC, tmp_path)

    assert [article.article_no for article in articles] == [1, 2]
    assert articles[0].text == "أ- ضبط الحالة. ب- تدوين الواقعات."
    assert articles[1].text == "وفقا للمادة (86) من هذا النظام."
    assert articles[1].page_no == 3
    assert articles[0].article_label == "المادة 1"
    assert articles[0].doc_id == SPEC.doc_id


def test_reports_every_invalid_row_and_duplicate_together(tmp_path: Path) -> None:
    """Wrong code, bad number, empty text and duplicates are all listed; nothing loads."""
    _write_table(
        tmp_path,
        [
            ("نظام", "CSR", 1, 1, "نص"),
            ("نظام", "CSL", "ثلاثة", 1, "نص"),
            ("نظام", "CSL", 4, 1, "  "),
            ("نظام", "CSL", 5, 1, "نص"),
            ("نظام", "CSL", 5, 1, "نص آخر"),
        ],
    )

    with pytest.raises(ArticleTableError) as error:
        read_article_table(SPEC, tmp_path)

    message = str(error.value)
    assert "row 2: code 'CSR'" in message
    assert "row 3: article number 'ثلاثة'" in message
    assert "row 4: article text is empty" in message
    assert "duplicated article numbers: [5]" in message


def test_missing_file_or_column_is_an_error(tmp_path: Path) -> None:
    """A missing table or a missing required column stops ingestion with a clear message."""
    with pytest.raises(ArticleTableError, match="missing"):
        read_article_table(SPEC, tmp_path)

    _write_table(tmp_path, [("نظام", "CSL", 1, 1)], header=HEADER[:-1])
    with pytest.raises(ArticleTableError, match="missing columns"):
        read_article_table(SPEC, tmp_path)


@pytest.mark.parametrize("spec", TABLE_DOCUMENT_SPECS, ids=lambda spec: spec.code)
def test_project_article_tables_have_every_article(spec) -> None:
    """Each committed table in data/raw/ loads and holds articles 1..expected exactly once."""
    articles = read_article_table(spec)

    assert [article.article_no for article in articles] == list(
        range(1, spec.expected_articles + 1)
    )
