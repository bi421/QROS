from __future__ import annotations

import os

import pytest


def pytest_addoption(parser) -> None:
    parser.addoption("--real-db", action="store_true", help="run real Supabase tenant-isolation tests")


@pytest.fixture(scope="session")
def real_db(request) -> bool:
    if not request.config.getoption("--real-db"):
        pytest.skip("real Supabase tests require --real-db")
    required = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        pytest.fail("missing real-db environment: " + ", ".join(missing))
    return True
