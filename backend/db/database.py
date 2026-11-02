"""Configure the PostgreSQL engine and initialize database metadata."""

import logging
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.db.config import DEFAULT_DATABASE_URL

load_dotenv()
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
engine = create_engine(DATABASE_URL)
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
