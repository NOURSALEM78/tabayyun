"""Load the processed regulatory knowledge workbook into PostgreSQL."""

import argparse
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Integer,
    String,
    case,
    func,
    insert,
    null,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.engine import Connection
from sqlalchemy.sql.schema import Column

from backend.db.database import engine, init_db
from backend.db.models import (
    Action,
    Article,
    Chunk,
    DecisionRule,
    Document,
    DocumentRelation,
    Employee,
    IngestionLog,
    Issuer,
    Procedure,
    ProcedureRequirement,
    Resource,
    Role,
)

logger = logging.getLogger(__name__)
WORKBOOK_PATH = Path("data/processed/Tabayyun_KB.xlsx")
SHEET_MODELS = (
    ("issuers", Issuer),
    ("documents", Document),
    ("articles", Article),
    ("chunks", Chunk),
    ("document_relations", DocumentRelation),
    ("procedures", Procedure),
    ("procedure_requirements", ProcedureRequirement),
    ("roles", Role),
    ("actions", Action),
    ("employees", Employee),
    ("resources", Resource),
    ("decision_rules", DecisionRule),
)


def convert_excel_value(value: Any, column: Column[Any]) -> Any:
    """Convert one workbook cell to the Python type expected by its database column."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None

    if isinstance(column.type, Boolean):
        if isinstance(value, bool):
            return value
        if value in (0, 1):
            return bool(value)
        if isinstance(value, str) and value.strip().lower() in {"true", "false", "1", "0"}:
            return value.strip().lower() in {"true", "1"}
        raise ValueError(f"Expected a boolean value, received {value!r}")

    if isinstance(column.type, Integer):
        if isinstance(value, bool):
            raise TypeError("Boolean values cannot be used as integers")
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f"Expected an integer value, received {value!r}")
        return int(value)

    if isinstance(column.type, DateTime):
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        return datetime.fromisoformat(str(value))

    if isinstance(column.type, Date):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    if isinstance(column.type, ARRAY):
        parsed = json.loads(value) if isinstance(value, str) else value
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ValueError(f"Expected {column.name} to be a JSON list of strings")
        return parsed

    if isinstance(column.type, String):
        return str(value)
    return value


def _embedding_if_text_unchanged(table: Any, statement: Any) -> Any:
    """Keep a chunk's embedding only while its text is unchanged; otherwise clear it.

    A cleared embedding is recomputed by ``python -m backend.retrieval.embed``.
    """
    return case(
        (table.c.text.is_distinct_from(statement.excluded.text), null()),
        else_=table.c.embedding,
    )


def _sheet_rows(connection: Connection, sheet: Any, model: Any) -> int:
    """Upsert a sheet's rows and report the sheet and Excel row on failure."""
    table = model.__table__
    header = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if header is None:
        raise ValueError(f"Sheet '{sheet.title}', row 1: missing header")

    headers = tuple(header)
    expected_columns = set(table.columns.keys())
    if sheet.title == "chunks":
        expected_columns.remove("embedding")
    if set(headers) != expected_columns or len(headers) != len(expected_columns):
        raise ValueError(
            f"Sheet '{sheet.title}', row 1: columns do not match the model; "
            f"expected {sorted(expected_columns)}, received {list(headers)}"
        )

    primary_key = table.primary_key.columns.values()[0]
    inserted_count = 0
    for row_number, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        try:
            if all(
                value is None or (isinstance(value, str) and not value.strip()) for value in values
            ):
                continue

            row: dict[str, Any] = {}
            for name, value in zip(headers, values, strict=True):
                column = table.c[name]
                converted = convert_excel_value(value, column)
                if converted is None and not column.nullable:
                    if column.server_default is not None:
                        continue
                    raise ValueError(f"Column '{name}' is required but its cell is empty")
                row[name] = converted

            statement = postgresql_insert(table).values(row)
            update_values = {
                column.name: statement.excluded[column.name]
                for column in table.columns
                if column.name != primary_key.name and column.name in row
            }
            if table.name == "chunks":
                update_values["embedding"] = _embedding_if_text_unchanged(table, statement)
            statement = statement.on_conflict_do_update(
                index_elements=[primary_key], set_=update_values
            )
            connection.execute(statement)
            inserted_count += 1
        except Exception as error:
            raise ValueError(f"Sheet '{sheet.title}', row {row_number}: {error}") from error

    return inserted_count


def _reset_sequences(connection: Connection) -> None:
    """Align imported integer primary-key sequences with their current maximum IDs."""
    for _, model in SHEET_MODELS:
        table = model.__table__
        primary_key = table.primary_key.columns.values()[0]
        if isinstance(primary_key.type, Integer):
            connection.execute(
                select(
                    func.setval(
                        func.pg_get_serial_sequence(table.name, primary_key.name),
                        func.coalesce(func.max(primary_key), 1),
                        func.max(primary_key).is_not(None),
                    )
                )
            )


def _mark_repealed_chunks(connection: Connection) -> None:
    """Mark chunks from repealed documents or articles as non-current."""
    repealed_documents = select(Document.doc_id).where(Document.status == "repealed")
    repealed_articles = select(Article.article_id).where(Article.status == "repealed")
    connection.execute(
        update(Chunk)
        .where(or_(Chunk.doc_id.in_(repealed_documents), Chunk.article_id.in_(repealed_articles)))
        .values(is_current=False)
    )


def _build_ingestion_log_values(source: str, docs_added: int) -> dict[str, int | str]:
    """Build an ingestion history row while leaving its primary key database-generated."""
    return {
        "source": source,
        "docs_added": docs_added,
        "docs_updated": 0,
        "docs_superseded": 0,
    }


def _insert_ingestion_log(connection: Connection, source: str, docs_added: int) -> None:
    """Append one ingestion history row and let PostgreSQL generate its run ID."""
    values = _build_ingestion_log_values(source, docs_added)
    connection.execute(insert(IngestionLog).values(values))


def seed_database(workbook_path: Path = WORKBOOK_PATH, reset: bool = False) -> None:
    """Initialize and transactionally upsert the workbook's supported data sheets."""
    init_db(reset=reset)
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        with engine.begin() as connection:
            row_counts = {
                sheet_name: _sheet_rows(connection, workbook[sheet_name], model)
                for sheet_name, model in SHEET_MODELS
            }
            _mark_repealed_chunks(connection)
            _reset_sequences(connection)
            _insert_ingestion_log(connection, str(workbook_path), row_counts["documents"])
            for sheet_name, model in SHEET_MODELS:
                count = connection.execute(select(func.count()).select_from(model.__table__))
                logger.info("%s: %d", sheet_name, count.scalar_one())
    finally:
        workbook.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load Tabayyun workbook data into PostgreSQL.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables first.")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    seed_database(reset=arguments.reset)
