"""Real Supabase tenant fixtures for P0 isolation tests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from supabase import Client, create_client

from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole


@dataclass(frozen=True)
class RealTenant:
    user_id: UUID
    workspace_id: UUID
    access_token: str
    context: TenantContext
    client: Client


@dataclass(frozen=True)
class RealTenantPair:
    service: Client
    a: RealTenant
    b: RealTenant


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--real-db",
        action="store_true",
        default=False,
        help="Run destructive real-Supabase tenant isolation tests.",
    )


@pytest.fixture(scope="session")
def real_db_enabled(pytestconfig: pytest.Config) -> bool:
    return bool(pytestconfig.getoption("--real-db"))


@pytest.fixture(scope="session")
def real_tenants(real_db_enabled: bool) -> RealTenantPair:
    if not real_db_enabled:
        pytest.skip("P0 real tenant tests require --real-db")

    url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    anon_key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not service_key or not anon_key:
        pytest.fail("SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and SUPABASE_ANON_KEY are required")

    service = create_client(url, service_key)

    created_users: list[UUID] = []
    workspace_ids: list[UUID] = []

    def make_tenant(label: str) -> RealTenant:
        user_id = uuid4()
        workspace_id = uuid4()
        email = f"qros-real-{label}-{user_id.hex[:12]}@test.invalid"
        password = f"QROS-real-{user_id.hex}-Isolation!9"

        response = service.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"qros_real_db_test": True},
            }
        )
        user = response.user
        if user is None:
            raise RuntimeError(f"failed to create test user {label}")
        user_id = UUID(str(user.id))
        created_users.append(user_id)

        service.table("workspace").insert(
            {"id": str(workspace_id), "name": f"QROS real tenant {label} {workspace_id}"}
        ).execute()
        workspace_ids.append(workspace_id)
        service.table("workspace_member").insert(
            {
                "workspace_id": str(workspace_id),
                "user_id": str(user_id),
                "role": WorkspaceRole.OWNER.value,
            }
        ).execute()

        session = create_client(url, anon_key).auth.sign_in_with_password(
            {"email": email, "password": password}
        )
        if session.session is None:
            raise RuntimeError(f"failed to sign in real test user {label}")
        token = session.session.access_token
        client = create_client(url, anon_key)
        client.postgrest.auth(token)

        return RealTenant(
            user_id=user_id,
            workspace_id=workspace_id,
            access_token=token,
            context=TenantContext(
                user_id=user_id,
                workspace_id=workspace_id,
                plan=Plan.FREE,
                role=WorkspaceRole.OWNER,
                access_token=token,
            ),
            client=client,
        )

    a = make_tenant("a")
    b = make_tenant("b")
    pair = RealTenantPair(service=service, a=a, b=b)

    try:
        yield pair
    finally:
        for workspace_id in workspace_ids:
            service.table("workspace_member").delete().eq("workspace_id", str(workspace_id)).execute()
            service.table("workspace").delete().eq("id", str(workspace_id)).execute()
        for user_id in created_users:
            service.auth.admin.delete_user(str(user_id))
