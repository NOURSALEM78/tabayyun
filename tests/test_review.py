"""Tests for the OCR review workbook export and import."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.ingestion.constants import (
    REVIEW_SHEET_CORRECTIONS,
    REVIEW_SHEET_PENDING,
    REVIEW_SHEET_REVIEWED,
    REVIEW_STATUS_CLEAN,
    SEED_CORRECTIONS_FILE,
    SEED_REVIEWED_FILE,
)
from backend.ingestion.corrections import TextCorrection, apply_text_corrections
from backend.ingestion.review_export import build_review_workbook
from backend.ingestion.review_import import ReviewImportError, import_review_workbook
from backend.ingestion.review_state import (
    load_reviewed_articles,
    save_reviewed_articles,
)
from backend.ingestion.split import ArticleRecord

ARTICLES = (
    ArticleRecord(1, "CSL", 1, "المادة الأولى", "يسري هذا النظام على المواطنين", page_no=1),
    ArticleRecord(
        2, "CSR", 1, "المادة 1", 'يتولى وكيل الوزارة للا"حوال المدنية الإشراف', page_no=2
    ),
    ArticleRecord(2, "CSR", 2, "المادة 2", "الآساس هو الوعاء الذي تحفظ فيه الوثائق", page_no=2),
)
OLD_CORRECTION = TextCorrection("CSL", 1, "المواطنين", "المواطنين جميعهم")


@pytest.fixture
def seed_dir(tmp_path: Path) -> Path:
    """Create seed files with one existing correction and CSL article 1 reviewed."""
    entry = {"doc": "CSL", "article": 1, "find": "المواطنين", "replace": "المواطنين جميعهم"}
    corrections = {"_note": "test", "corrections": [entry]}
    (tmp_path / SEED_CORRECTIONS_FILE).write_text(
        json.dumps(corrections, ensure_ascii=False), encoding="utf-8"
    )
    save_reviewed_articles({("CSL", 1)}, tmp_path / SEED_REVIEWED_FILE)
    return tmp_path


def _corrected() -> tuple[ArticleRecord, ...]:
    """Return the test articles after the existing correction, as the pipeline would."""
    return apply_text_corrections(ARTICLES, [OLD_CORRECTION])


def _filled_workbook(tmp_path: Path, rows: list[list[object]], clean_row: int | None) -> Path:
    """Export a workbook, then fill correction rows and optionally mark a pending row clean."""
    workbook, _, _ = build_review_workbook(_corrected(), [OLD_CORRECTION], {("CSL", 1)})
    pending = workbook[REVIEW_SHEET_PENDING]
    status_column = [cell.value for cell in pending[1]].index("نتيجة المراجعة") + 1
    if clean_row is not None:
        pending.cell(row=clean_row, column=status_column, value=REVIEW_STATUS_CLEAN)
    sheet = workbook[REVIEW_SHEET_CORRECTIONS]
    for offset, values in enumerate(rows, start=2):
        for column, value in enumerate(values, start=1):
            sheet.cell(row=offset, column=column, value=value)
    path = tmp_path / "filled.xlsx"
    workbook.save(path)
    return path


def test_export_splits_pending_and_reviewed() -> None:
    workbook, pending, reviewed = build_review_workbook(
        _corrected(), [OLD_CORRECTION], {("CSR", 2)}
    )
    assert (pending, reviewed) == (1, 2)
    pending_codes = [
        row[1:3] for row in workbook[REVIEW_SHEET_PENDING].iter_rows(min_row=2, values_only=True)
    ]
    assert pending_codes == [("CSR", 1)]
    assert workbook[REVIEW_SHEET_REVIEWED].max_row == 3
    assert workbook[REVIEW_SHEET_PENDING].sheet_view.rightToLeft


def test_import_appends_corrections_and_marks_reviewed(tmp_path: Path, seed_dir: Path) -> None:
    path = _filled_workbook(tmp_path, [["csr", 1, 'للا"حوال', "للأحوال", None]], clean_row=3)

    result = import_review_workbook(path, _corrected(), seed_dir)

    saved = json.loads((seed_dir / SEED_CORRECTIONS_FILE).read_text(encoding="utf-8"))
    assert saved["corrections"][-1] == {
        "doc": "CSR",
        "article": 1,
        "find": 'للا"حوال',
        "replace": "للأحوال",
    }
    assert result.reviewed == {("CSR", 1), ("CSR", 2)}
    assert load_reviewed_articles(seed_dir / SEED_REVIEWED_FILE) == {
        ("CSL", 1),
        ("CSR", 1),
        ("CSR", 2),
    }


def test_import_skips_rows_already_imported(tmp_path: Path, seed_dir: Path) -> None:
    path = _filled_workbook(tmp_path, [["CSL", 1, "المواطنين", "المواطنين جميعهم", None]], None)

    result = import_review_workbook(path, _corrected(), seed_dir)

    assert (result.duplicates, result.corrections) == (1, [])


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (["CSR", 9, "نص", "صواب", None], "رقم المادة غير صحيح"),
        (["CSR", 2, "غير موجود", "صواب", None], "غير موجود"),
        (["CSR", 2, "الوثائق", "الوثائق", None], "مطابق للصواب"),
    ],
)
def test_import_rejects_bad_rows_and_writes_nothing(
    tmp_path: Path, seed_dir: Path, row: list[object], message: str
) -> None:
    before = (seed_dir / SEED_CORRECTIONS_FILE).read_text(encoding="utf-8")
    path = _filled_workbook(tmp_path, [row], clean_row=2)

    with pytest.raises(ReviewImportError) as error:
        import_review_workbook(path, _corrected(), seed_dir)

    assert message in error.value.problems[0]
    assert (seed_dir / SEED_CORRECTIONS_FILE).read_text(encoding="utf-8") == before
    assert load_reviewed_articles(seed_dir / SEED_REVIEWED_FILE) == {("CSL", 1)}


def test_later_corrections_see_earlier_ones_in_the_same_import(
    tmp_path: Path, seed_dir: Path
) -> None:
    rows = [
        ["CSR", 2, "الآساس هو", "الأساس هو", None],
        ["CSR", 2, "الأساس هو الوعاء", "الأساس هو الملف", None],
    ]
    path = _filled_workbook(tmp_path, rows, None)

    result = import_review_workbook(path, _corrected(), seed_dir)

    assert len(result.corrections) == 2
