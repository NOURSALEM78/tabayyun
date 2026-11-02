"""Write extracted knowledge and validation findings to an Excel workbook."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from backend.ingestion.constants import EXPORT_COLUMNS, EXPORT_PATH
from backend.ingestion.extract import ExtractionResult
from backend.ingestion.validate import ValidationRow

logger = logging.getLogger(__name__)


def _without_embeddings(chunks: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    """Return chunk rows without vector data for spreadsheet export."""
    return [{key: value for key, value in chunk.items() if key != "embedding"} for chunk in chunks]


def _excel_value(value: Any) -> Any:
    """Convert timezone-aware timestamps to Excel-compatible UTC-naive values."""
    if isinstance(value, datetime) and value.utcoffset() is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _excel_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert row values to types supported by Excel worksheets."""
    return [{column: _excel_value(value) for column, value in row.items()} for row in rows]


def write_workbook(
    result: ExtractionResult,
    validation_rows: tuple[ValidationRow, ...],
    output_path: Path = EXPORT_PATH,
) -> Path:
    """Write one worksheet per requested table and the two review reports."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheets: dict[str, list[dict[str, Any]]] = {
        "issuers": list(result.issuers),
        "documents": list(result.documents),
        "articles": list(result.articles),
        "chunks": _without_embeddings(result.chunks),
        "document_relations": list(result.document_relations),
        "procedures": list(result.procedures),
        "procedure_requirements": list(result.procedure_requirements),
        "roles": list(result.roles),
        "actions": list(result.actions),
        "employees": list(result.employees),
        "resources": list(result.resources),
        "decision_rules": list(result.decision_rules),
        "validation": [dict(row) for row in validation_rows],
        "amendment_markers": list(result.amendment_markers),
    }

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, rows in sheets.items():
            dataframe = pd.DataFrame(_excel_rows(rows), columns=EXPORT_COLUMNS[sheet_name])
            dataframe.to_excel(writer, sheet_name=sheet_name, index=False)
    logger.info("Wrote ingestion workbook to %s", output_path)
    return output_path
