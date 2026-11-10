"""Configure the PostgreSQL engine and initialize database metadata."""

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.settings import settings

logger = logging.getLogger(__name__)

DATABASE_URL: str = settings.database_url
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class from which all database models inherit."""


# Columns made optional after the tables were first created. create_all does not change
# existing tables, so these statements bring older databases in line (safe to repeat).
SCHEMA_UPDATES: tuple[str, ...] = (
    "ALTER TABLE access_requests ALTER COLUMN approver_role_id DROP NOT NULL",
    "ALTER TABLE access_requests ALTER COLUMN approved_at DROP NOT NULL",
    "ALTER TABLE access_requests ALTER COLUMN approver_note DROP NOT NULL",
)


def init_db(reset: bool = False) -> None:
    """Create registered tables, optionally dropping the schema first."""
    from backend.db.models import Base as ModelBase

    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        if reset:
            ModelBase.metadata.drop_all(bind=connection)
        ModelBase.metadata.create_all(bind=connection)
        for statement in SCHEMA_UPDATES:
            connection.execute(text(statement))
    logger.info("Database schema initialized")


if __name__ == "__main__":
    from backend.db.database import init_db as initialize_database

    initialize_database()
