from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from researchos.saas.auth.authorization import ACTIONS, POLICY, RESOURCES, is_allowed, require_permission
from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole


def context(role: WorkspaceRole) -> TenantContext:
    return TenantContext(
        user_id=uuid4(),
        workspace_id=uuid4(),
        plan=Plan.PRO,
        role=role,
    )


@pytest.mark.parametrize("role", list(WorkspaceRole))
@pytest.mark.parametrize("resource", RESOURCES)
@pytest.mark.parametrize("action", ACTIONS)
def test_every_role_resource_action_matches_executable_matrix(
    role: WorkspaceRole,
    resource: str,
    action: str,
) -> None:
    assert is_allowed(role, resource, action) is POLICY[role][resource][action]


def test_viewer_cannot_create_job() -> None:
    app = FastAPI()

    @app.post("/v1/test-job")
    @require_permission("job", "create")
    def create_job(tenant: TenantContext = Depends(lambda: context(WorkspaceRole.VIEWER))) -> dict[str, str]:
        return {"status": "created"}

    response = TestClient(app).post("/v1/test-job")
    assert response.status_code == 403
    assert response.json()["detail"] == "permission denied: job:create"


def test_researcher_cannot_delete_workspace() -> None:
    app = FastAPI()

    @app.delete("/v1/test-workspace")
    @require_permission("workspace", "delete")
    def delete_workspace(
        tenant: TenantContext = Depends(lambda: context(WorkspaceRole.RESEARCHER)),
    ) -> dict[str, str]:
        return {"status": "deleted"}

    response = TestClient(app).delete("/v1/test-workspace")
    assert response.status_code == 403
    assert response.json()["detail"] == "permission denied: workspace:delete"


def test_missing_tenant_context_is_fail_closed() -> None:
    app = FastAPI()

    @app.get("/v1/test")
    @require_permission("dataset", "read")
    def read_dataset() -> dict[str, str]:
        return {"status": "visible"}

    response = TestClient(app).get("/v1/test")
    assert response.status_code == 500
    assert response.json()["detail"] == "authorization context is missing"


@pytest.mark.parametrize("role", list(WorkspaceRole))
def test_allowed_capability_executes(role: WorkspaceRole) -> None:
    app = FastAPI()

    @app.get("/v1/test")
    @require_permission("dataset", "read")
    def read_dataset(tenant: TenantContext = Depends(lambda: context(role))) -> dict[str, str]:
        return {"status": "visible"}

    response = TestClient(app).get("/v1/test")
    assert response.status_code == (200 if is_allowed(role, "dataset", "read") else 403)
