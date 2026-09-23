from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from researchos.saas.auth.permissions import Action, POLICY, Resource, Role, is_allowed, require_permission
from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole


def context(role: WorkspaceRole) -> TenantContext:
    return TenantContext(
        user_id=uuid4(),
        workspace_id=uuid4(),
        plan=Plan.PRO,
        role=role,
    )


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("resource", list(Resource))
@pytest.mark.parametrize("action", list(Action))
def test_every_role_resource_action_matches_executable_matrix(
    role: Role,
    resource: Resource,
    action: Action,
) -> None:
    assert is_allowed(role, resource, action) is (action in POLICY[role][resource])


def test_viewer_cannot_create_job() -> None:
    app = FastAPI()

    def viewer_context() -> TenantContext:
        return context(WorkspaceRole.VIEWER)

    @app.post("/v1/test-job")
    @require_permission("job", "create")
    def create_job(
        tenant: TenantContext = Depends(viewer_context),
    ) -> dict[str, str]:
        return {"status": "created"}

    response = TestClient(app).post(
        "/v1/test-job",
        headers={"X-Request-ID": "authz-viewer-test"},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["detail"]["code"] == "FORBIDDEN"
    assert body["detail"]["request_id"] == "authz-viewer-test"


def test_researcher_cannot_delete_workspace() -> None:
    app = FastAPI()

    def researcher_context() -> TenantContext:
        return context(WorkspaceRole.RESEARCHER)

    @app.delete("/v1/test-workspace")
    @require_permission("workspace", "delete")
    def delete_workspace(
        tenant: TenantContext = Depends(researcher_context),
    ) -> dict[str, str]:
        return {"status": "deleted"}

    response = TestClient(app).delete("/v1/test-workspace")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "FORBIDDEN"


def test_missing_tenant_context_is_fail_closed() -> None:
    app = FastAPI()

    @app.get("/v1/test")
    @require_permission("dataset", "read")
    def read_dataset() -> dict[str, str]:
        return {"status": "visible"}

    response = TestClient(app).get("/v1/test")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("role", list(WorkspaceRole))
def test_allowed_capability_executes(role: WorkspaceRole) -> None:
    app = FastAPI()

    def role_context() -> TenantContext:
        return context(role)

    @app.get("/v1/test")
    @require_permission("dataset", "read")
    def read_dataset(
        tenant: TenantContext = Depends(role_context),
    ) -> dict[str, str]:
        return {"status": "visible"}

    response = TestClient(app).get("/v1/test")
    assert response.status_code == (200 if is_allowed(role, Resource.DATASET, Action.READ) else 403)
