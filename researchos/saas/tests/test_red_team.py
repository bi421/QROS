"""Red-team regression tests for the SaaS security boundary."""

from __future__ import annotations

import inspect
import logging

import pytest
from io import BytesIO
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from researchos.saas.api import create_app
from researchos.saas.contracts import Plan, TenantContext
from researchos.saas.datasets import InMemoryDatasetStorage, InMemoryDatasetStore
from researchos.saas.store import InMemoryResearchJobStore
from researchos.saas.supabase_auth import SupabaseJwtAuthProvider
from researchos.saas.worker import ResearchWorker


class _StaticAuth:
    def __init__(self, context: TenantContext) -> None:
        self.context = context

    def authenticate(self, authorization: str | None) -> TenantContext:
        if authorization != "Bearer test":
            raise RuntimeError("unexpected test authorization")
        return self.context


class _ExplodingStorage(InMemoryDatasetStorage):
    def put(self, storage_path: str, file: Any) -> None:
        raise RuntimeError(
            "traceback: SELECT * FROM secret; SUPABASE_SERVICE_ROLE_KEY=super-secret"
        )


class _RejectingSupabaseAuth:
    def get_claims(self, token: str) -> dict[str, object]:
        if token == "forged-tenant-token":
            raise ValueError("invalid JWT signature")
        return {"claims": {"sub": str(uuid4()), "tenant_id": str(uuid4())}}


class _Membership:
    def __init__(self, workspace_id: Any) -> None:
        self.workspace_id = workspace_id

    def resolve(self, user_id: Any) -> tuple[Any, Plan]:
        return self.workspace_id, Plan.PRO


def _client(context: TenantContext, *, storage: Any = None, raise_server_exceptions: bool = True) -> TestClient:
    return TestClient(
        create_app(
            auth_provider=_StaticAuth(context),
            job_store=InMemoryResearchJobStore(),
            dataset_store=InMemoryDatasetStore(),
            dataset_storage=storage or InMemoryDatasetStorage(),
        ),
        raise_server_exceptions=raise_server_exceptions,
    )


def test_jwt_tamper_tenant_id_is_rejected() -> None:
    provider = SupabaseJwtAuthProvider(
        _RejectingSupabaseAuth(),
        _Membership(uuid4()),
    )

    try:
        provider.authenticate("Bearer forged-tenant-token")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 401
    else:
        raise AssertionError("forged JWT was accepted")


def test_storage_path_traversal_is_rejected() -> None:
    client = _client(TenantContext(uuid4(), uuid4(), Plan.PRO))

    response = client.post(
        "/v1/datasets",
        headers={"Authorization": "Bearer test"},
        data={"name": "../../../etc/passwd"},
        files={"file": ("payload.csv", BytesIO(b"x"), "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "INVALID_PATH"


def test_job_id_enumeration_never_leaks_existence() -> None:
    client = _client(TenantContext(uuid4(), uuid4(), Plan.PRO))

    for _ in range(16):
        response = client.get(
            f"/v1/research-runs/{uuid4()}",
            headers={"Authorization": "Bearer test"},
        )
        assert response.status_code == 404
        assert response.status_code != 403


def test_error_leak_is_blocked() -> None:
    request_id = "red-team-error-001"
    client = _client(
        TenantContext(uuid4(), uuid4(), Plan.PRO),
        storage=_ExplodingStorage(),
        raise_server_exceptions=False,
    )

    response = client.post(
        "/v1/datasets",
        headers={"Authorization": "Bearer test", "X-Request-ID": request_id},
        data={"name": "safe-name"},
        files={"file": ("payload.csv", BytesIO(b"x"), "text/csv")},
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload["detail"] == "Internal error"
    assert payload["error"] == {
        "code": "internal_error",
        "message": "Internal error",
        "request_id": request_id,
    }
    body = response.text
    assert "traceback" not in body.lower()
    assert "service_role" not in body.lower()
    assert "sql" not in body.lower()
    assert "SELECT" not in body
    assert "SUPABASE_SERVICE_ROLE_KEY" not in body
    assert response.headers["X-Request-ID"] == request_id


def test_service_role_bypass_is_not_part_of_worker_boundary(caplog: pytest.LogCaptureFixture) -> None:
    source = inspect.getsource(ResearchWorker)
    assert "service_role" not in source
    assert "SUPABASE_SERVICE_ROLE_KEY" not in source

    caplog.set_level(logging.DEBUG)
    workspace_id = uuid4()
    job_id = uuid4()
    assert job_id is not None
    assert workspace_id is not None
    assert all(
        "service_role" not in record.getMessage().lower()
        and "supabase_service_role_key" not in record.getMessage().lower()
        for record in caplog.records
    )
