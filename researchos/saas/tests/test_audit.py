from datetime import datetime, timezone
from uuid import uuid4

import pytest

from researchos.saas.audit import AuditEvent, InMemoryAuditEventStore


WORKSPACE = uuid4()


def test_audit_event_requires_non_empty_action_and_resource_type() -> None:
    with pytest.raises(ValueError, match="action"):
        AuditEvent(
            id=uuid4(),
            workspace_id=WORKSPACE,
            action="",
            resource_type="artifact",
            resource_id=None,
            actor_user_id=None,
            request_id=None,
            metadata={},
            created_at=datetime.now(timezone.utc),
        )

    with pytest.raises(ValueError, match="resource_type"):
        AuditEvent(
            id=uuid4(),
            workspace_id=WORKSPACE,
            action="delete",
            resource_type="",
            resource_id=None,
            actor_user_id=None,
            request_id=None,
            metadata={},
            created_at=datetime.now(timezone.utc),
        )


def test_audit_event_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        AuditEvent(
            id=uuid4(),
            workspace_id=WORKSPACE,
            action="delete",
            resource_type="artifact",
            resource_id="artifact-1",
            actor_user_id=None,
            request_id=None,
            metadata={},
            created_at=datetime(2026, 9, 19),
        )


def test_in_memory_store_is_tenant_scoped_and_append_only() -> None:
    other_workspace = uuid4()
    store = InMemoryAuditEventStore()
    own = AuditEvent.create(
        workspace_id=WORKSPACE,
        action="deletion_approved",
        resource_type="artifact",
        resource_id="artifact-1",
        metadata={"reason": "retention_window_elapsed"},
    )
    other = AuditEvent.create(
        workspace_id=other_workspace,
        action="deletion_approved",
        resource_type="artifact",
        resource_id="artifact-2",
    )

    store.append(own)
    store.append(other)

    assert store.list(WORKSPACE) == [own]
    assert store.list(other_workspace) == [other]


def test_audit_event_metadata_is_copied_at_creation() -> None:
    metadata = {"safe": True}
    event = AuditEvent.create(
        workspace_id=WORKSPACE,
        action="security_sensitive_action",
        resource_type="research_run",
        metadata=metadata,
    )
    metadata["safe"] = False
    assert event.metadata == {"safe": True}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("action", "x" * 129),
        ("resource_type", "x" * 129),
        ("resource_id", "x" * 257),
        ("request_id", "x" * 129),
    ],
)
def test_audit_event_bounds_sensitive_identifiers(field: str, value: str) -> None:
    kwargs: dict[str, object] = {
        "action": "delete",
        "resource_type": "artifact",
        "resource_id": None,
        "request_id": None,
    }
    kwargs[field] = value
    with pytest.raises(ValueError, match="maximum length"):
        AuditEvent.create(workspace_id=WORKSPACE, **kwargs)
