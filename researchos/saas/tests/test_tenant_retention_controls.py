from __future__ import annotations

from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient

from researchos.saas.api import create_app
from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole
from researchos.saas.persistence import InMemoryTenantPersistence, RetentionConfig


class StaticAuth:
    def __init__(self, context: TenantContext) -> None:
        self.context = context

    def authenticate(self, authorization: str | None, requested_workspace_id=None) -> TenantContext:
        assert authorization == "Bearer test"
        if requested_workspace_id is not None and requested_workspace_id != self.context.workspace_id:
            raise ValueError("workspace mismatch")
        return self.context


def test_soft_delete_marks_all_rows_and_schedules_free_retention() -> None:
    workspace_id = uuid4()
    persistence = InMemoryTenantPersistence()
    persistence.add("dataset", "dataset-1", workspace_id, {"id": "dataset-1", "name": "sample"})
    persistence.add("research_run", "job-1", workspace_id, {"id": "job-1"})
    persistence.add("evidence", "evidence-1", workspace_id, {"id": "evidence-1", "hash": "a" * 64})

    receipt = persistence.soft_delete_workspace(workspace_id)

    assert receipt.retention_days == 30
    assert receipt.scheduled_purge_at > receipt.deleted_at
    assert persistence.visible("dataset", workspace_id) == []
    assert persistence.visible("research_run", workspace_id) == []
    assert persistence.visible("evidence", workspace_id) == []


def test_custom_retention_window_is_configurable() -> None:
    workspace_id = uuid4()
    persistence = InMemoryTenantPersistence()
    receipt = persistence.soft_delete_workspace(
        workspace_id,
        retention=RetentionConfig(retention_days=90),
    )
    assert receipt.retention_days == 90
    assert receipt.scheduled_purge_at > receipt.deleted_at


def test_workspace_delete_returns_receipt_and_blocks_follow_up_list_reads() -> None:
    workspace_id = uuid4()
    context = TenantContext(uuid4(), workspace_id, Plan.FREE, WorkspaceRole.OWNER)
    persistence = InMemoryTenantPersistence()
    persistence.add("dataset", "dataset-1", workspace_id, {"id": "dataset-1", "name": "sample"})

    client = TestClient(
        create_app(
            auth_provider=StaticAuth(context),
            tenant_persistence=persistence,
        )
    )

    response = client.delete(
        f"/v1/workspaces/{workspace_id}",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["workspace_id"] == str(workspace_id)
    assert body["retention_days"] == 30
    assert body["scheduled_purge_date"]
    assert body["receipt_id"]

    list_response = client.get(
        "/v1/datasets",
        headers={"Authorization": "Bearer test"},
    )
    assert list_response.status_code == 410
    assert list_response.json()["message"] == "workspace is deleted"


def test_export_contains_datasets_jobs_and_evidence_envelopes() -> None:
    workspace_id = uuid4()
    context = TenantContext(uuid4(), workspace_id, Plan.FREE, WorkspaceRole.OWNER)
    persistence = InMemoryTenantPersistence()
    persistence.add("dataset", "dataset-1", workspace_id, {"id": "dataset-1", "name": "sample"})
    persistence.add("research_run", "job-1", workspace_id, {"id": "job-1", "status": "succeeded"})
    persistence.add(
        "evidence",
        "evidence-1",
        workspace_id,
        {"id": "evidence-1", "envelope_hash": "b" * 64},
    )

    client = TestClient(
        create_app(
            auth_provider=StaticAuth(context),
            tenant_persistence=persistence,
        )
    )

    response = client.get(
        f"/v1/workspaces/{workspace_id}/export",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    with ZipFile(BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert {"datasets.json", "jobs.json", "evidence_envelopes.json"} <= names
        assert "dataset-1" in archive.read("datasets.json").decode("utf-8")
        assert "job-1" in archive.read("jobs.json").decode("utf-8")
        assert "evidence-1" in archive.read("evidence_envelopes.json").decode("utf-8")
