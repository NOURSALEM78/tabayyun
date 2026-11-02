"""Initialize schema without inventing regulatory or access-control data."""

import logging

from backend.db.database import init_db

logger = logging.getLogger(__name__)


def seed_database() -> None:
    """Initialize database tables without adding unsupported seed records."""
    init_db()
    logger.info("Database initialized; no seed records were added")


if __name__ == "__main__":
    seed_database()
