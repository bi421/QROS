from __future__ import annotations

from uuid import uuid4

import pytest

from researchos.saas.contracts import ResearchJob, ResearchJobStatus
from researchos.saas.supabase_job_store import SupabaseResearchJobStore


class _Response:
    def __init__(self, data):
        self.data = data


class _InsertQuery:
    def __init__(self, rows):
        self._rows = rows

    def insert(self, row):
        self._rows.append(row)
        return self

    def select(self, *_args, **_kwargs):
        return self

    def execute(self):
        row = self._rows[-1]
        return _Response([{**row, "attempt_count": 0, "max_attempts": 3, "error_code": None}])


class _Client:
    def __init__(self):
        self.rows = []
        self.insert_called = False

    def table(self, name):
        assert name == "research_run"
        self.insert_called = True
        return _InsertQuery(self.rows)


def _job(workspace_id):
    return ResearchJob(
        id=uuid4(),
        workspace_id=workspace_id,
        dataset_version_id=uuid4(),
        workflow_id="golden-path.v1",
        status=ResearchJobStatus.QUEUED,
        source_dataset_sha256="a" * 64,
        created_by=uuid4(),
    )


def test_create_rejects_cross_tenant_job_before_database_write() -> None:
    workspace_id = uuid4()
    other_workspace_id = uuid4()
    client = _Client()
    store = SupabaseResearchJobStore(client)

    with pytest.raises(ValueError, match="workspace"):
        store.create(workspace_id, _job(other_workspace_id))

    assert client.insert_called is False
    assert client.rows == []


def test_create_accepts_matching_tenant_and_writes_workspace_id() -> None:
    workspace_id = uuid4()
    client = _Client()
    store = SupabaseResearchJobStore(client)

    job = _job(workspace_id)
    created = store.create(workspace_id, job)

    assert client.insert_called is True
    assert created.workspace_id == workspace_id
