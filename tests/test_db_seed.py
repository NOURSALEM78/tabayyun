"""Tests for Excel-to-database value conversion."""

from backend.db.models import Article, Procedure
from backend.db.seed import _build_ingestion_log_values, convert_excel_value


def test_empty_excel_values_convert_to_none() -> None:
    """Treat blank strings and empty cells as SQL NULL values."""
    column = Article.__table__.c.approver_text

    assert convert_excel_value("", column) is None
    assert convert_excel_value("   ", column) is None
    assert convert_excel_value(None, column) is None


def test_json_aliases_convert_to_python_list() -> None:
    """Parse the workbook's JSON-encoded aliases into a Python list."""
    column = Procedure.__table__.c.aliases

    assert convert_excel_value('["طلب", "معاملة"]', column) == ["طلب", "معاملة"]


def test_excel_boolean_values_convert_to_python_bool() -> None:
    """Preserve native Excel booleans and parse equivalent text values."""
    column = Article.__table__.c.requires_approval

    assert convert_excel_value(True, column) is True
    assert convert_excel_value(False, column) is False
    assert convert_excel_value("false", column) is False
    assert convert_excel_value("1", column) is True


def test_ingestion_log_builder_leaves_run_id_to_database() -> None:
    """Build log values without supplying the database-generated run ID."""
    values = _build_ingestion_log_values("data/processed/Tabayyun_KB.xlsx", 11)

    assert values == {
        "source": "data/processed/Tabayyun_KB.xlsx",
        "docs_added": 11,
        "docs_updated": 0,
        "docs_superseded": 0,
    }
    assert "run_id" not in values
