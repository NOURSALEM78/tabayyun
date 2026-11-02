"""Provide isolated environment configuration for test imports."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
