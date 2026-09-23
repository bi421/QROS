from __future__ import annotations

import os
from uuid import uuid4

import pytest
from supabase import Client, create_client


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


@pytest.fixture(scope="session")
def service_client(real_db: bool) -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def _authenticated_client(service: Client, email: str, password: str) -> tuple[Client, str]:
    created = service.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    user_id = str(created.user.id)
    session = service.auth.sign_in_with_password({"email": email, "password": password})
    if session.session is None:
        raise AssertionError("Supabase did not issue a user session")
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"]), session.session.access_token


def _with_token(client: Client, token: str) -> Client:
    client.postgrest.auth(token)
    return client


def test_real_supabase_dataset_rls_isolation(service_client: Client) -> None:
    user_a = f"qros-rls-a-{uuid4().hex[:12]}@example.invalid"
    user_b = f"qros-rls-b-{uuid4().hex[:12]}@example.invalid"
    password = "QrosRealDb!2026-Temporary"
    client_a, token_a = _authenticated_client(service_client, user_a, password)
    client_b, token_b = _authenticated_client(service_client, user_b, password)
    workspace_a = str(uuid4())
    workspace_b = str(uuid4())
    dataset_id = str(uuid4())
    try:
        service_client.table("workspace").insert({"id": workspace_a, "name": "tenant-a"}).execute()
        service_client.table("workspace").insert({"id": workspace_b, "name": "tenant-b"}).execute()
        service_client.table("workspace_member").insert(
            {"workspace_id": workspace_a, "user_id": str(service_client.auth.admin.get_user_by_id(str(service_client.auth.get_user_by_id(str(uuid4())) if False else "")))}
        )
    except Exception:
        # Membership creation requires the user IDs returned above; use a fresh deterministic
        # cleanup path below rather than hiding a security failure.
        raise
    finally:
        for workspace in (workspace_a, workspace_b):
            service_client.table("workspace").delete().eq("id", workspace).execute()
