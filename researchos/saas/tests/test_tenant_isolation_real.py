from __future__ import annotations

import os
from uuid import uuid4

import pytest
from supabase import Client, create_client


def _authenticated_client(service: Client, email: str, password: str) -> tuple[Client, str, str]:
    created = service.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    user_id = str(created.user.id)
    session = service.auth.sign_in_with_password({"email": email, "password": password})
    if session.session is None:
        raise AssertionError("Supabase did not issue a user session")
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
    client.postgrest.auth(session.session.access_token)
    return client, session.session.access_token, user_id


def test_real_supabase_dataset_rls_isolation(service_client: Client) -> None:
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

        own = client_a.table("dataset").select("id").eq("id", dataset_id).execute()
        foreign = client_b.table("dataset").select("id").eq("id", dataset_id).execute()
        assert len(own.data or []) == 1
        assert foreign.data == []

        foreign_list = client_b.table("dataset").select("id").execute()
        assert dataset_id not in {str(row["id"]) for row in (foreign_list.data or [])}

        denied_insert = client_b.table("dataset").insert(
            {
                "id": str(uuid4()),
                "workspace_id": workspace_a,
                "name": "cross-tenant-write",
                "created_by": user_b,
            }
        ).execute()
        assert denied_insert.data in (None, [])

    finally:
        service_client.table("dataset").delete().eq("id", dataset_id).execute()
        service_client.table("workspace_member").delete().in_("user_id", [user_a, user_b]).execute()
        service_client.table("workspace").delete().in_("id", [workspace_a, workspace_b]).execute()
        service_client.auth.admin.delete_user(user_a)
        service_client.auth.admin.delete_user(user_b)
