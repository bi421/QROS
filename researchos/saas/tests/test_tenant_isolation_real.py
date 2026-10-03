from __future__ import annotations

import os
from collections.abc import Callable
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError
from supabase import Client, create_client

# Tenant tables whose authenticated grants are revoked by
# 202609170004_saas_server_only_data_api.sql.
SERVER_ONLY_TABLES = (
    "workspace",
    "workspace_member",
    "subscription",
    "dataset",
    "dataset_version",
    "research_run",
    "artifact",
    "evidence",
    "usage_event",
    "audit_log",
)


def _authenticated_client(service: Client, email: str, password: str) -> tuple[Client, str, str]:
    created = service.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    user_id = str(created.user.id)
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
    session = client.auth.sign_in_with_password({"email": email, "password": password})
    if session.session is None:
        raise AssertionError("Supabase did not issue a user session")
    client.postgrest.auth(session.session.access_token)
    return client, session.session.access_token, user_id


def _assert_denied(action: Callable[[], object]) -> None:
    with pytest.raises(APIError) as exc:
        action()
    code = getattr(exc.value, "code", None)
    assert code == "42501", f"expected permission denied (42501), got: {exc.value}"


def test_real_supabase_data_api_is_server_only(service_client: Client) -> None:
    password = "QrosRealDb!2026-Temporary"
    email_a = f"qros-rls-a-{uuid4().hex[:12]}@example.invalid"
    email_b = f"qros-rls-b-{uuid4().hex[:12]}@example.invalid"
    client_a, _, user_a = _authenticated_client(service_client, email_a, password)
    client_b, _, user_b = _authenticated_client(service_client, email_b, password)
    workspace_a = str(uuid4())
    workspace_b = str(uuid4())
    dataset_id = str(uuid4())
    try:
        service_client.table("workspace").insert({"id": workspace_a, "name": "tenant-a"}).execute()
        service_client.table("workspace").insert({"id": workspace_b, "name": "tenant-b"}).execute()
        service_client.table("workspace_member").insert(
            {"workspace_id": workspace_a, "user_id": user_a, "role": "owner"}
        ).execute()
        service_client.table("workspace_member").insert(
            {"workspace_id": workspace_b, "user_id": user_b, "role": "owner"}
        ).execute()
        service_client.table("dataset").insert(
            {
                "id": dataset_id,
                "workspace_id": workspace_a,
                "name": "tenant-a-private",
                "created_by": user_a,
            }
        ).execute()

        # The privileged server path works and sees the row.
        seen = service_client.table("dataset").select("id").eq("id", dataset_id).execute()
        assert len(seen.data or []) == 1

        # Direct Data API reads are denied for every tenant table, for both tenants.
        for client in (client_a, client_b):
            for table in SERVER_ONLY_TABLES:
                _assert_denied(lambda c=client, t=table: c.table(t).select("*").limit(1).execute())

        # Direct Data API writes are denied, including cross-tenant writes.
        _assert_denied(
            lambda: (
                client_b.table("dataset")
                .insert(
                    {
                        "id": str(uuid4()),
                        "workspace_id": workspace_a,
                        "name": "cross-tenant-write",
                        "created_by": user_b,
                    }
                )
                .execute()
            )
        )
        _assert_denied(
            lambda: (
                client_b.table("dataset")
                .update({"name": "hijacked"})
                .eq("id", dataset_id)
                .execute()
            )
        )
        _assert_denied(lambda: client_b.table("dataset").delete().eq("id", dataset_id).execute())

        # Denied writes must not have changed anything.
        after = service_client.table("dataset").select("name").eq("id", dataset_id).execute()
        assert after.data == [{"name": "tenant-a-private"}]
    finally:
        service_client.table("dataset").delete().eq("id", dataset_id).execute()
        service_client.table("workspace_member").delete().in_("user_id", [user_a, user_b]).execute()
        service_client.table("workspace").delete().in_("id", [workspace_a, workspace_b]).execute()
        service_client.auth.admin.delete_user(user_a)
        service_client.auth.admin.delete_user(user_b)
