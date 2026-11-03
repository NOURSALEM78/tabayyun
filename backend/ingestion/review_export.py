"""Export the OCR review workbook: articles still to review, reviewed ones, corrections.

Run with ``python -m backend.ingestion.review_export``. The team fills the yellow
columns and loads the result back with ``backend.ingestion.review_import``.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from backend.ingestion.constants import (
    DOCUMENT_SPECS,
    REVIEW_COL_APPLIED,
    REVIEW_COL_ARTICLE,
    REVIEW_COL_CODE,
    REVIEW_COL_DOCUMENT,
    REVIEW_COL_FILE,
    REVIEW_COL_FIND,
    REVIEW_COL_NOTES,
    REVIEW_COL_PAGE,
    REVIEW_COL_REPLACE,
    REVIEW_COL_STATUS,
    REVIEW_COL_TEXT,
    REVIEW_EXPORT_PATH,
    REVIEW_GUIDE_LINES,
    REVIEW_SHEET_CORRECTIONS,
    REVIEW_SHEET_GUIDE,
    REVIEW_SHEET_PENDING,
    REVIEW_SHEET_REVIEWED,
    REVIEW_STATUSES,
)
from backend.ingestion.corrections import TextCorrection, load_text_corrections
from backend.ingestion.review_state import (
    ArticleKey,
    load_reviewed_articles,
    reviewed_keys,
)
from backend.ingestion.run_all import load_corrected_articles
from backend.ingestion.split import ArticleRecord

logger = logging.getLogger(__name__)

ARTICLE_COLUMNS: tuple[tuple[str, int], ...] = (
    (REVIEW_COL_DOCUMENT, 24),
    (REVIEW_COL_CODE, 8),
    (REVIEW_COL_ARTICLE, 9),
    (REVIEW_COL_FILE, 24),
    (REVIEW_COL_PAGE, 9),
    (REVIEW_COL_TEXT, 90),
    (REVIEW_COL_APPLIED, 12),
    (REVIEW_COL_STATUS, 14),
    (REVIEW_COL_NOTES, 30),
)
CORRECTION_COLUMNS: tuple[tuple[str, int], ...] = (
    (REVIEW_COL_CODE, 8),
    (REVIEW_COL_ARTICLE, 10),
    (REVIEW_COL_FIND, 45),
    (REVIEW_COL_REPLACE, 45),
    (REVIEW_COL_NOTES, 30),
)
EDITABLE_ARTICLE_COLUMNS = frozenset({REVIEW_COL_STATUS, REVIEW_COL_NOTES})
EMPTY_CORRECTION_ROWS = 300
HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
EDIT_FILL = PatternFill("solid", fgColor="FFF2CC")
THIN_SIDE = Side(style="thin", color="BFBFBF")
CELL_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)
CELL_ALIGNMENT = Alignment(wrap_text=True, vertical="top", horizontal="right")


@dataclass(frozen=True, slots=True)
class ReviewExportSummary:
    """Counts written to the review workbook."""

    pending: int
    reviewed: int
    path: Path


def _article_row(article: ArticleRecord, applied: Counter[ArticleKey]) -> list[object]:
    """Build one article row in ARTICLE_COLUMNS order (editable cells start empty)."""
    spec = next(spec for spec in DOCUMENT_SPECS if spec.code == article.document_code)
    key = (article.document_code, article.article_no)
    return [
        spec.title,
        spec.code,
        article.article_no,
        spec.source_filename,
        article.page_no,
        article.text,
        applied.get(key, 0),
        None,
        None,
    ]


def _write_table(
    sheet: Worksheet,
    columns: Sequence[tuple[str, int]],
    rows: Sequence[Sequence[object]],
    editable: frozenset[str],
) -> None:
    """Write a right-to-left table with a styled header and highlighted editable columns."""
    sheet.sheet_view.rightToLeft = True
    sheet.append([name for name, _ in columns])
    for index, (name, width) in enumerate(columns, start=1):
        header = sheet.cell(row=1, column=index)
        sheet.column_dimensions[header.column_letter].width = width
        header.font, header.fill, header.border = HEADER_FONT, HEADER_FILL, CELL_BORDER
        header.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in rows:
        sheet.append(list(row))
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment, cell.border = CELL_ALIGNMENT, CELL_BORDER
            if columns[cell.column - 1][0] in editable:
                cell.fill = EDIT_FILL
    sheet.freeze_panes = "A2"


def _add_status_choices(sheet: Worksheet, row_count: int) -> None:
    """Restrict the review-status column to the allowed values."""
    names = [name for name, _ in ARTICLE_COLUMNS]
    letter = sheet.cell(row=1, column=names.index(REVIEW_COL_STATUS) + 1).column_letter
    validation = DataValidation(
        type="list", formula1=f'"{",".join(REVIEW_STATUSES)}"', allow_blank=True
    )
    sheet.add_data_validation(validation)
    validation.add(f"{letter}2:{letter}{max(row_count, 1) + 1}")


def _write_guide(sheet: Worksheet) -> None:
    """Write the review instructions sheet."""
    sheet.sheet_view.rightToLeft = True
    sheet.column_dimensions["A"].width = 110
    for line in REVIEW_GUIDE_LINES:
        sheet.append([line])
        sheet.cell(row=sheet.max_row, column=1).alignment = CELL_ALIGNMENT
    sheet["A1"].font = Font(bold=True, size=14)


def build_review_workbook(
    articles: Sequence[ArticleRecord],
    corrections: Sequence[TextCorrection],
    reviewed: set[ArticleKey],
) -> tuple[Workbook, int, int]:
    """Split articles into pending and reviewed sheets; return the workbook and both counts."""
    applied = Counter((item.doc, item.article) for item in corrections)
    done = reviewed_keys(reviewed, corrections)
    pending_rows, reviewed_rows = [], []
    for article in articles:
        is_done = (article.document_code, article.article_no) in done
        (reviewed_rows if is_done else pending_rows).append(_article_row(article, applied))

    workbook = Workbook()
    _write_guide(workbook.active)
    workbook.active.title = REVIEW_SHEET_GUIDE
    for title, rows in (
        (REVIEW_SHEET_PENDING, pending_rows),
        (REVIEW_SHEET_REVIEWED, reviewed_rows),
    ):
        sheet = workbook.create_sheet(title)
        _write_table(sheet, ARTICLE_COLUMNS, rows, EDITABLE_ARTICLE_COLUMNS)
        _add_status_choices(sheet, len(rows))
    empty_rows = [[None] * len(CORRECTION_COLUMNS)] * EMPTY_CORRECTION_ROWS
    editable = frozenset(name for name, _ in CORRECTION_COLUMNS)
    corrections_sheet = workbook.create_sheet(REVIEW_SHEET_CORRECTIONS)
    _write_table(corrections_sheet, CORRECTION_COLUMNS, empty_rows, editable)
    return workbook, len(pending_rows), len(reviewed_rows)


def export_review_workbook(
    articles: Sequence[ArticleRecord], path: Path = REVIEW_EXPORT_PATH
) -> ReviewExportSummary:
    """Write the review workbook for the given corrected articles."""
    workbook, pending, reviewed = build_review_workbook(
        articles, load_text_corrections(), load_reviewed_articles()
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    logger.info("Review workbook: %s (pending=%d, reviewed=%d)", path, pending, reviewed)
    return ReviewExportSummary(pending=pending, reviewed=reviewed, path=path)


def main() -> None:
    """Build the review workbook from the current OCR text and corrections."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    export_review_workbook(load_corrected_articles())


if __name__ == "__main__":
    main()
