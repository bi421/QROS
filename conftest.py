"""Repository-wide pytest options for release verification."""
from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--real-db",
        action="store_true",
        default=False,
        help="enable tests that require a real PostgreSQL/Supabase database",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "real_db: test requires --real-db and a real database"
    )
