"""Tests for loading application settings from environment variables."""

import pytest

from backend.settings import Settings


def test_settings_reads_database_url_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read the database URL from the configured environment variable."""
    database_url = "sqlite://"
    monkeypatch.setenv("DATABASE_URL", database_url)

    assert Settings(_env_file=None).database_url == database_url
