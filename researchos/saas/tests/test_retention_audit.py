from datetime import datetime, timezone
from uuid import uuid4

from researchos.saas.audit import InMemoryAuditEventStore
from researchos.saas.retention import DeletionCandidate
from researchos.saas.retention_audit import retention_audit_callback


def test_retention_audit_callback_binds_authorized_workspace() -> None:
    store = InMemoryAuditEventStore()
    workspace = uuid4()
    actor = uuid4()
    request_id = "req-123"
    candidate = DeletionCandidate(
        resource_type="artifact",
        resource_id="artifact-1",
        created_at=datetime.now(timezone.utc),
    )

    callback = retention_audit_callback(
        store,
        workspace_id=workspace,
        actor_user_id=actor,
        request_id=request_id,
    )
    callback(candidate, "deletion_approved")

    events = store.list(workspace)
    assert len(events) == 1
    event = events[0]
    assert event.workspace_id == workspace
    assert event.actor_user_id == actor
    assert event.request_id == request_id
    assert event.action == "deletion_approved"
    assert event.resource_type == "artifact"
    assert event.resource_id == "artifact-1"


def test_retention_audit_callback_does_not_use_resource_id_as_tenant() -> None:
    store = InMemoryAuditEventStore()
    workspace_a = uuid4()
    workspace_b = uuid4()
    candidate = DeletionCandidate(
        resource_type="dataset",
        resource_id=str(workspace_b),
        created_at=datetime.now(timezone.utc),
    )

    retention_audit_callback(store, workspace_id=workspace_a)(candidate, "deletion_completed")

    assert len(store.list(workspace_a)) == 1
    assert store.list(workspace_b) == []


def test_retention_audit_callback_writes_only_non_secret_context() -> None:
    store = InMemoryAuditEventStore()
    workspace = uuid4()
    candidate = DeletionCandidate(
        resource_type="dataset_version",
        resource_id="version-1",
        created_at=datetime.now(timezone.utc),
        reference_count=0,
        legal_hold=False,
    )

    retention_audit_callback(store, workspace_id=workspace)(candidate, "deletion_approved")

    event = store.list(workspace)[0]
    assert event.metadata == {"reference_count": 0, "legal_hold": False}
