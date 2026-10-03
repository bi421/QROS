from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from researchos.saas.api import create_app
from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole
from researchos.saas.datasets import InMemoryDatasetStorage, InMemoryDatasetStore
from researchos.saas.queue import InMemoryResearchJobQueue
from researchos.saas.store import InMemoryResearchJobStore
from researchos.saas.workspace import (
    InMemoryWorkspaceProvisioner,
    WorkspaceProvisioningResult,
)


class ProvisioningAuth:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        self.context: TenantContext | None = None

    def authenticate_user(self, authorization: str | None) -> UUID:
        if authorization != "Bearer test":
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="missing bearer token")
        return self.user_id

    def authenticate(self, authorization: str | None) -> TenantContext:
        if authorization != "Bearer test":
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="missing bearer token")
        if self.context is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="workspace access denied")
        return self.context


def _client():
    user_id = uuid4()
    auth = ProvisioningAuth(user_id)
    provisioner = InMemoryWorkspaceProvisioner()
    datasets = InMemoryDatasetStore()
    client = TestClient(
        create_app(
            auth_provider=auth,
            workspace_provisioner=provisioner,
            dataset_store=datasets,
            dataset_storage=InMemoryDatasetStorage(),
            job_store=InMemoryResearchJobStore(),
            job_queue=InMemoryResearchJobQueue(),
        )
    )
    return client, auth, provisioner, datasets


def test_authenticated_user_can_provision_workspace_as_owner_with_free_plan() -> None:
    client, auth, provisioner, _ = _client()
    response = client.post(
        "/v1/workspaces",
        headers={"Authorization": "Bearer test"},
        json={"name": "Customer Research"},
    )
    assert response.status_code == 201
    payload = response.json()
    result = provisioner._owners[auth.user_id]
    assert UUID(payload["workspace_id"]) == result.workspace_id
    assert payload["role"] == "owner"
    assert payload["plan"] == "free"

    auth.context = TenantContext(
        auth.user_id, result.workspace_id, Plan.FREE, WorkspaceRole.OWNER
    )
    me = client.get("/v1/me", headers={"Authorization": "Bearer test"})
    assert me.status_code == 200
    assert me.json() == {
        "user_id": str(auth.user_id),
        "workspace_id": str(result.workspace_id),
        "plan": "free",
    }


def test_unauthenticated_workspace_provisioning_is_rejected() -> None:
    client, _, _, _ = _client()
    response = client.post("/v1/workspaces", json={"name": "No Auth"})
    assert response.status_code == 401


def test_request_cannot_supply_arbitrary_owner_identity() -> None:
    client, _, _, _ = _client()
    response = client.post(
        "/v1/workspaces",
        headers={"Authorization": "Bearer test"},
        json={"name": "Owned By Caller", "user_id": str(uuid4())},
    )
    assert response.status_code == 400


def test_second_provisioning_is_rejected_without_creating_another_workspace() -> None:
    client, auth, provisioner, _ = _client()
    first = client.post(
        "/v1/workspaces",
        headers={"Authorization": "Bearer test"},
        json={"name": "First"},
    )
    assert first.status_code == 201
    second = client.post(
        "/v1/workspaces",
        headers={"Authorization": "Bearer test"},
        json={"name": "Second"},
    )
    assert second.status_code == 409
    assert len(provisioner._owners) == 1
    assert provisioner._owners[auth.user_id].workspace_id == UUID(
        first.json()["workspace_id"]
    )


def test_workspace_provisioning_failure_fails_closed_without_local_state() -> None:
    class FailingProvisioner(InMemoryWorkspaceProvisioner):
        def provision(self, user_id: UUID, name: str) -> WorkspaceProvisioningResult:
            raise RuntimeError("database unavailable")

    auth = ProvisioningAuth(uuid4())
    client = TestClient(
        create_app(auth_provider=auth, workspace_provisioner=FailingProvisioner())
    )
    response = client.post(
        "/v1/workspaces",
        headers={"Authorization": "Bearer test"},
        json={"name": "Should Not Exist"},
    )
    assert response.status_code == 503
    assert auth.context is None


def test_new_workspace_can_continue_to_dataset_and_research_run() -> None:
    client, auth, _, datasets = _client()
    created = client.post(
        "/v1/workspaces",
        headers={"Authorization": "Bearer test"},
        json={"name": "Research Customer"},
    )
    assert created.status_code == 201
    workspace_id = UUID(created.json()["workspace_id"])
    auth.context = TenantContext(
        auth.user_id, workspace_id, Plan.FREE, WorkspaceRole.OWNER
    )

    dataset = client.post(
        "/v1/datasets",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "dataset-1"},
        data={"name": "xauusd"},
        files={"file": ("xauusd.csv", b"timestamp,open\n1,1\n", "text/csv")},
    )
    assert dataset.status_code == 201
    version_id = dataset.json()["version"]["id"]
    assert datasets.get_dataset(workspace_id, UUID(dataset.json()["id"])) is not None

    run = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "run-1"},
        json={"dataset_version_id": version_id},
    )
    assert run.status_code == 202
    assert run.json()["workspace_id"] == str(workspace_id)
