"""Pytest controls for real Supabase tenant-isolation integration tests."""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--real-db",
        action="store_true",
        default=False,
        help="run integration tests against the configured real Supabase project",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "real_db: requires a real Supabase persistence boundary")


@pytest.fixture(scope="session")
def real_db(request: pytest.FixtureRequest) -> bool:
    enabled = bool(request.config.getoption("--real-db"))
    if not enabled:
        pytest.skip("real Supabase integration requires --real-db")
    return True
