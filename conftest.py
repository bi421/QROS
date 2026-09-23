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
        "markers",
        "real_db: test requires a real PostgreSQL/Supabase database",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--real-db"):
        return
    skip = pytest.mark.skip(reason="requires --real-db")
    for item in items:
        if "real_db" in item.keywords:
            item.add_marker(skip)
