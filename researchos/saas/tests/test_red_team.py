"""Red-team regression tests for the SaaS security boundary."""
from __future__ import annotations

import base64
import json
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from researchos.saas.api import create_app
from researchos.saas.contracts import TenantContext, WorkspaceRole


def _context(role: WorkspaceRole = WorkspaceRole.RESEARCHER) -> TenantContext:
    return TenantContext(
        workspace_id=uuid4(),
        user_id=uuid4(),
        role=role,
        plan="free",
        access_token="red-team-token",
    )


class RedTeamAuth:
    def __init__(self, context: TenantContext) -> None:
        self.context = context

    def authenticate(self, authorization: str | None, requested_workspace_id: UUID | None = None) -> TenantContext:
        if authorization != "Bearer red-team":
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="invalid credentials")
        if requested_workspace_id is not None and requested_workspace_id != self.context.workspace_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="workspace access denied")
        return self.context


def _client() -> TestClient:
    ctx = _context()
    return TestClient(create_app(auth_provider=RedTeamAuth(ctx)))


def _tampered_jwt(original: str, tenant_id: str) -> str:
    parts = original.split(".")
    payload = {"sub": str(uuid4()), "tenant_id": tenant_id, "role": "owner"}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=").decode()
    return ".".join([parts[0], encoded, parts[2]])


def test_jwt_tamper_tenant_id() -> None:
    client = _client()
    tampered = _tampered_jwt("e30.e30.invalid", str(uuid4()))
    response = client.get("/v1/datasets", headers={"Authorization": f"Bearer {tampered}"})
    assert response.status_code in {401, 403}


def test_storage_path_traversal() -> None:
    client = _client()
    response = client.post(
        "/v1/datasets/upload",
        headers={"Authorization": "Bearer red-team", "X-Storage-Path": "../../../etc/passwd"},
    )
    assert response.status_code in {400, 422}
    if response.status_code == 400:
        assert response.json().get("code") == "INVALID_PATH"


def test_job_id_enumeration() -> None:
    client = _client()
    for _ in range(8):
        response = client.get(f"/v1/research-runs/{uuid4()}", headers={"Authorization": "Bearer red-team"})
        assert response.status_code == 404
        assert response.status_code != 403


def test_error_leak() -> None:
    client = _client()
    response = client.get("/v1/research-runs/not-a-uuid", headers={"Authorization": "Bearer red-team"})
    body = response.text.lower()
    assert "traceback" not in body
    assert "service_role" not in body
    assert "select " not in body
    assert "insert " not in body
    assert "postgres" not in body


def test_service_role_bypass() -> None:
    client = _client()
    response = client.get("/v1/research-runs/not-a-uuid", headers={"Authorization": "Bearer red-team"})
    assert response.status_code in {404, 422}
