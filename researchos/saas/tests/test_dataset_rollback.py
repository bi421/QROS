from io import BytesIO
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from researchos.saas.api import create_app
from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole
from researchos.saas.datasets import DatasetVersion, InMemoryDatasetStorage, InMemoryDatasetStore


class StaticAuth:
    def __init__(self, context: TenantContext) -> None:
        self.context = context

    def authenticate(self, authorization: str | None, requested_workspace_id=None) -> TenantContext:
        assert authorization == "Bearer test"
        if requested_workspace_id is not None and requested_workspace_id != self.context.workspace_id:
            raise RuntimeError("workspace mismatch")
        return self.context


class FailingVersionStore(InMemoryDatasetStore):
    def create_version(self, workspace_id: UUID, version: DatasetVersion) -> DatasetVersion:
        raise RuntimeError("simulated version persistence failure")


def test_failed_initial_dataset_upload_rolls_back_metadata_and_object() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    store = FailingVersionStore()
    storage = InMemoryDatasetStorage()
    client = TestClient(
        create_app(
            auth_provider=StaticAuth(context),
            dataset_store=store,
            dataset_storage=storage,
        )
    )

    response = client.post(
        "/v1/datasets",
        headers={"Authorization": "Bearer test"},
        data={"name": "sample"},
        files={"file": ("sample.csv", BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )

    assert response.status_code == 500
    assert store._datasets == {}
    assert store._versions == {}
    assert storage._objects == {}
