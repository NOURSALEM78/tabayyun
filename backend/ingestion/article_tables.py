"""Read reviewed article tables (one Excel row per article) from data/raw/.

A document whose ``DocumentSpec.table_filename`` is set is read from its table
instead of OCR. The team copies each article from the source and checks it, so
the text is used as written: only Arabic-Indic digits are converted and
whitespace is collapsed, the same as for OCR text.

Required columns (first sheet, header in row 1): الرمز, رقم المادة,
نص المادة الحالي. The optional column صفحة الـ PDF is kept as the page number.
One table may hold several documents (e.g. a law and its regulation from the same
PDF): each document takes the rows with its own code. Every problem in a table
is reported together and nothing is loaded.
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from openpyxl import load_workbook

from backend.ingestion.clean import collapse_whitespace, convert_arabic_digits
from backend.ingestion.constants import (
    ARTICLE_PREFIX,
    ARTICLE_TABLE_REQUIRED_COLUMNS,
    RAW_DATA_DIR,
    REVIEW_COL_ARTICLE,
    REVIEW_COL_CODE,
    REVIEW_COL_PAGE,
    REVIEW_COL_TEXT,
    TABLE_DOCUMENT_SPECS,
    DocumentSpec,
)
from backend.ingestion.split import ArticleRecord

logger = logging.getLogger(__name__)

TableRow = dict[str, object]


class ArticleTableError(ValueError):
    """Raised when an article table is missing or has invalid rows."""


def table_path(spec: DocumentSpec, raw_dir: Path = RAW_DATA_DIR) -> Path:
    """Return the path of a document's article table."""
    return raw_dir / spec.table_filename


def table_hash(spec: DocumentSpec, raw_dir: Path = RAW_DATA_DIR) -> str:
    """Return the SHA-256 of a document's article table file."""
    return hashlib.sha256(table_path(spec, raw_dir).read_bytes()).hexdigest()


def _rows(path: Path) -> Iterator[tuple[int, TableRow]]:
    """Yield (Excel row number, row by header) for every non-empty row of the first sheet."""
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        values = sheet.iter_rows(values_only=True)
        header = [str(cell).strip() if cell is not None else "" for cell in next(values, ())]
        missing = [name for name in ARTICLE_TABLE_REQUIRED_COLUMNS if name not in header]
        if missing:
            raise ArticleTableError(f"{path.name}: missing columns {missing}")
        for row_number, row in enumerate(values, start=2):
            if any(cell not in (None, "") for cell in row):
                yield row_number, dict(zip(header, row, strict=False))
    finally:
        workbook.close()


def _as_int(value: object) -> int | None:
    """Return a whole number from an Excel cell, or None when it is not one."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and convert_arabic_digits(value.strip()).isdigit():
        return int(convert_arabic_digits(value.strip()))
    return None


def _codes_sharing_table(spec: DocumentSpec) -> set[str]:
    """Return the codes of every configured document that uses the same table as spec."""
    return {spec.code} | {
        other.code for other in TABLE_DOCUMENT_SPECS if other.table_filename == spec.table_filename
    }


def _article_from_row(
    spec: DocumentSpec, row_number: int, row: TableRow, problems: list[str]
) -> ArticleRecord | None:
    """Build one article from a table row, or record why the row is invalid.

    Returns None without a problem for a valid row of another document in the table.
    """
    code = str(row.get(REVIEW_COL_CODE) or "").strip()
    allowed_codes = _codes_sharing_table(spec)
    if code != spec.code and code in allowed_codes:
        return None
    number = _as_int(row.get(REVIEW_COL_ARTICLE))
    text = collapse_whitespace(convert_arabic_digits(str(row.get(REVIEW_COL_TEXT) or "")))
    row_problems = []
    if code not in allowed_codes:
        row_problems.append(f"code {code!r} is not one of {sorted(allowed_codes)}")
    if number is None:
        row_problems.append(f"article number {row.get(REVIEW_COL_ARTICLE)!r} is not a number")
    if not text:
        row_problems.append("article text is empty")
    if row_problems:
        problems.append(f"row {row_number}: " + "; ".join(row_problems))
        return None
    assert number is not None  # narrowed above
    return ArticleRecord(
        doc_id=spec.doc_id,
        document_code=spec.code,
        article_no=number,
        article_label=f"{ARTICLE_PREFIX} {number}",
        text=text,
        page_no=_as_int(row.get(REVIEW_COL_PAGE)),
    )


def read_article_table(
    spec: DocumentSpec, raw_dir: Path = RAW_DATA_DIR
) -> tuple[ArticleRecord, ...]:
    """Read and check one document's article table, sorted by article number.

    Raises ArticleTableError listing every invalid row and duplicated number.
    Missing or extra article numbers are left to validate.py, which reports them
    the same way for every document.
    """
    path = table_path(spec, raw_dir)
    if not path.is_file():
        raise ArticleTableError(f"Article table for {spec.code} is missing: {path}")

    problems: list[str] = []
    articles = [
        article
        for row_number, row in _rows(path)
        if (article := _article_from_row(spec, row_number, row, problems)) is not None
    ]
    duplicates = sorted(n for n, c in Counter(a.article_no for a in articles).items() if c > 1)
    if duplicates:
        problems.append(f"duplicated article numbers: {duplicates}")
    if problems:
        raise ArticleTableError(f"{path.name} has invalid rows:\n- " + "\n- ".join(problems))

    logger.info("Read %d articles for %s from %s", len(articles), spec.code, path.name)
    return tuple(sorted(articles, key=lambda article: article.article_no))
