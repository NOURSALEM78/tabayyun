"""Load a filled OCR review workbook back into the seed files.

Run with ``python -m backend.ingestion.review_import <workbook.xlsx>``.

* Rows in the corrections sheet are appended to ``text_corrections.json``.
* Articles with a review status (clean or has errors) are added to
  ``reviewed_articles.json`` so they leave the pending sheet next time.

Every correction is checked against the current article text first: its wrong text
must appear exactly once. If any row has a problem, all problems are reported and
nothing is written, so a half-imported review never happens.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from backend.ingestion.constants import (
    REVIEW_COL_ARTICLE,
    REVIEW_COL_CODE,
    REVIEW_COL_FIND,
    REVIEW_COL_REPLACE,
    REVIEW_COL_STATUS,
    REVIEW_SHEET_CORRECTIONS,
    REVIEW_SHEET_PENDING,
    REVIEW_SHEET_REVIEWED,
    REVIEW_STATUSES,
    SEED_CORRECTIONS_FILE,
    SEED_DATA_DIR,
    SEED_REVIEWED_FILE,
)
from backend.ingestion.corrections import (
    TextCorrection,
    append_text_corrections,
    load_text_corrections,
)
from backend.ingestion.review_state import (
    ArticleKey,
    load_reviewed_articles,
    save_reviewed_articles,
)
from backend.ingestion.run_all import load_corrected_articles
from backend.ingestion.split import ArticleRecord

logger = logging.getLogger(__name__)


class ReviewImportError(ValueError):
    """Raised when a review workbook has rows that cannot be applied."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__(f"{len(problems)} problem(s) in the review workbook")
        self.problems = tuple(problems)


@dataclass(slots=True)
class ReviewImport:
    """Everything read from one workbook, before it is written."""

    corrections: list[TextCorrection] = field(default_factory=list)
    reviewed: set[ArticleKey] = field(default_factory=set)
    duplicates: int = 0
    problems: list[str] = field(default_factory=list)


def _rows(sheet: Worksheet, required: Sequence[str]) -> Iterator[tuple[int, dict[str, object]]]:
    """Yield (Excel row number, {header: value}) for non-empty rows, found by header text."""
    headers = [str(cell.value).strip() if cell.value else "" for cell in sheet[1]]
    missing = [name for name in required if name not in headers]
    if missing:
        raise ReviewImportError([f"ورقة «{sheet.title}» ينقصها العمود: {', '.join(missing)}"])
    for number, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        row = dict(zip(headers, values, strict=False))
        if any(value not in (None, "") for value in row.values()):
            yield number, row


def _article_key(row: dict[str, object]) -> ArticleKey | None:
    """Read the document code and article number, or None when they are invalid."""
    code = str(row.get(REVIEW_COL_CODE) or "").strip().upper()
    try:
        return code, int(str(row.get(REVIEW_COL_ARTICLE)).strip())
    except ValueError:
        return None


def _read_statuses(sheet: Worksheet, texts: dict[ArticleKey, str], result: ReviewImport) -> None:
    """Collect articles that were given a review status in one article sheet."""
    required = (REVIEW_COL_CODE, REVIEW_COL_ARTICLE, REVIEW_COL_STATUS)
    for number, row in _rows(sheet, required):
        status = str(row.get(REVIEW_COL_STATUS) or "").strip()
        if not status:
            continue
        key = _article_key(row)
        if status not in REVIEW_STATUSES:
            result.problems.append(f"«{sheet.title}» سطر {number}: حالة غير معروفة «{status}»")
        elif key not in texts:
            result.problems.append(f"«{sheet.title}» سطر {number}: المادة غير موجودة")
        else:
            result.reviewed.add(key)


def _check_correction(
    number: int, row: dict[str, object], texts: dict[ArticleKey, str]
) -> TextCorrection | str:
    """Return a correction that applies cleanly to the current text, or a problem message."""
    key = _article_key(row)
    find = str(row.get(REVIEW_COL_FIND) or "").strip()
    fix = str(row.get(REVIEW_COL_REPLACE) or "").strip()
    prefix = f"«{REVIEW_SHEET_CORRECTIONS}» سطر {number}"
    if key not in texts:
        return f"{prefix}: الرمز أو رقم المادة غير صحيح"
    if not find or find == fix:
        return f"{prefix}: النص الخطأ فارغ أو مطابق للصواب"
    count = texts[key].count(find)
    if count != 1:
        where = "غير موجود" if count == 0 else f"مكرر {count} مرات"
        return f"{prefix}: النص الخطأ {where} في المادة {key[1]}؛ انسخيه كما هو مع كلمات حوله"
    return TextCorrection(key[0], key[1], find, fix)


def _read_corrections(
    sheet: Worksheet,
    texts: dict[ArticleKey, str],
    existing: set[TextCorrection],
    result: ReviewImport,
) -> None:
    """Validate correction rows in order, applying each to the text before checking the next.

    Rows already in text_corrections.json are counted and skipped, so importing the same
    workbook twice never applies a correction twice.
    """
    required = (REVIEW_COL_CODE, REVIEW_COL_ARTICLE, REVIEW_COL_FIND, REVIEW_COL_REPLACE)
    for number, row in _rows(sheet, required):
        if TextCorrection(*_row_fields(row)) in existing:
            result.duplicates += 1
            continue
        checked = _check_correction(number, row, texts)
        if isinstance(checked, str):
            result.problems.append(checked)
            continue
        key = (checked.doc, checked.article)
        texts[key] = texts[key].replace(checked.find, checked.replace)
        result.corrections.append(checked)
        result.reviewed.add(key)


def _row_fields(row: dict[str, object]) -> tuple[str, int, str, str]:
    """Return the raw correction fields of a row (used to recognise rows already imported)."""
    key = _article_key(row) or ("", 0)
    find = str(row.get(REVIEW_COL_FIND) or "").strip()
    return key[0], key[1], find, str(row.get(REVIEW_COL_REPLACE) or "").strip()


def read_review_workbook(
    path: Path, articles: Sequence[ArticleRecord], existing: Sequence[TextCorrection]
) -> ReviewImport:
    """Read and validate a filled workbook against the current (corrected) article texts."""
    workbook = load_workbook(path, data_only=True)
    texts = {(article.document_code, article.article_no): article.text for article in articles}
    result = ReviewImport()
    for title in (REVIEW_SHEET_PENDING, REVIEW_SHEET_REVIEWED):
        if title in workbook.sheetnames:
            _read_statuses(workbook[title], texts, result)
    if REVIEW_SHEET_CORRECTIONS in workbook.sheetnames:
        _read_corrections(workbook[REVIEW_SHEET_CORRECTIONS], texts, set(existing), result)
    return result


def import_review_workbook(
    path: Path, articles: Sequence[ArticleRecord], seed_dir: Path = SEED_DATA_DIR
) -> ReviewImport:
    """Validate the workbook, then append corrections and update the reviewed list."""
    corrections_path = seed_dir / SEED_CORRECTIONS_FILE
    reviewed_path = seed_dir / SEED_REVIEWED_FILE
    result = read_review_workbook(path, articles, load_text_corrections(corrections_path))
    if result.problems:
        raise ReviewImportError(result.problems)
    if result.corrections:
        append_text_corrections(result.corrections, corrections_path)
    save_reviewed_articles(load_reviewed_articles(reviewed_path) | result.reviewed, reviewed_path)
    logger.info(
        "Imported %d new corrections, %d reviewed articles (%d rows already imported)",
        len(result.corrections),
        len(result.reviewed),
        result.duplicates,
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    """Import a review workbook; return a non-zero exit code when it has problems."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Import a filled OCR review workbook.")
    parser.add_argument("workbook", type=Path, help="path to the filled review .xlsx file")
    arguments = parser.parse_args(argv)
    try:
        import_review_workbook(arguments.workbook, load_corrected_articles())
    except ReviewImportError as error:
        for problem in error.problems:
            logger.error(problem)
        logger.error("Nothing was saved. Fix the rows above and run the import again.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
