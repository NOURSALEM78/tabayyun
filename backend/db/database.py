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


def init_db() -> None:
    """Create the pgvector extension and all tables registered on Base."""
    from backend.db.models import Base as ModelBase

    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    ModelBase.metadata.create_all(bind=engine)
    logger.info("Database schema initialized")


if __name__ == "__main__":
    from backend.db.database import init_db as initialize_database

    initialize_database()
