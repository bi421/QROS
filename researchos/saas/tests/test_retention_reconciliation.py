from uuid import uuid4

import pytest

from researchos.saas.retention_reconciliation import (
    DeletionOperation,
    DeletionOperationState,
    InMemoryDeletionOperationStore,
    require_reconciliation_after_delete,
)


def test_reconciliation_state_is_durable_in_operation_store() -> None:
    store = InMemoryDeletionOperationStore()
    workspace_id = uuid4()

    store.put(
        DeletionOperation(
            workspace_id=workspace_id,
            operation_id="delete-artifact-1",
            resource_type="artifact",
            resource_id="artifact-1",
            state=DeletionOperationState.DELETE_ATTEMPTED,
        )
    )

    operation = require_reconciliation_after_delete(
        store=store,
        workspace_id=workspace_id,
        operation_id="delete-artifact-1",
        resource_type="artifact",
        resource_id="artifact-1",
    )

    assert operation.state is DeletionOperationState.RECONCILIATION_REQUIRED
    assert store.get(workspace_id, "delete-artifact-1") == operation


def test_operation_state_is_tenant_scoped() -> None:
    store = InMemoryDeletionOperationStore()
    workspace_a = uuid4()
    workspace_b = uuid4()

    operation = DeletionOperation(
        workspace_id=workspace_a,
        operation_id="delete-1",
        resource_type="dataset",
        resource_id="dataset-1",
        state=DeletionOperationState.APPROVED,
    )
    store.put(operation)

    assert store.get(workspace_a, "delete-1") == operation
    assert store.get(workspace_b, "delete-1") is None


def test_operation_rejects_empty_identity() -> None:
    workspace_id = uuid4()

    for operation_id, resource_type, resource_id in [
        ("", "artifact", "artifact-1"),
        ("delete-1", "", "artifact-1"),
        ("delete-1", "artifact", ""),
    ]:
        with pytest.raises(ValueError):
            DeletionOperation(
                workspace_id=workspace_id,
                operation_id=operation_id,
                resource_type=resource_type,
                resource_id=resource_id,
                state=DeletionOperationState.APPROVED,
            )


def test_operation_state_transition_contract() -> None:
    workspace_id = uuid4()
    operation = DeletionOperation(
        workspace_id=workspace_id,
        operation_id="delete-1",
        resource_type="artifact",
        resource_id="artifact-1",
        state=DeletionOperationState.APPROVED,
    )

    attempted = operation.transition_to(DeletionOperationState.DELETE_ATTEMPTED)
    completed = attempted.transition_to(DeletionOperationState.COMPLETED)
    assert attempted.state is DeletionOperationState.DELETE_ATTEMPTED
    assert completed.state is DeletionOperationState.COMPLETED

    with pytest.raises(ValueError):
        completed.transition_to(DeletionOperationState.APPROVED)

    with pytest.raises(ValueError):
        operation.transition_to(DeletionOperationState.COMPLETED)


def test_in_memory_transition_preserves_resource_identity() -> None:
    store = InMemoryDeletionOperationStore()
    workspace_id = uuid4()
    store.put(
        DeletionOperation(
            workspace_id=workspace_id,
            operation_id="delete-1",
            resource_type="artifact",
            resource_id="artifact-1",
            state=DeletionOperationState.APPROVED,
        )
    )

    updated = store.transition(
        workspace_id,
        "delete-1",
        "artifact",
        "artifact-1",
        DeletionOperationState.DELETE_ATTEMPTED,
    )
    assert updated.state is DeletionOperationState.DELETE_ATTEMPTED

    with pytest.raises(ValueError):
        store.transition(
            workspace_id,
            "delete-1",
            "dataset",
            "dataset-1",
            DeletionOperationState.COMPLETED,
        )


def test_supabase_row_adapter_is_strict_and_tenant_scoped() -> None:
    from researchos.saas.retention_reconciliation import _operation_from_row

    workspace_id = uuid4()
    operation = _operation_from_row(
        {
            "workspace_id": str(workspace_id),
            "operation_id": "delete-1",
            "resource_type": "artifact",
            "resource_id": "artifact-1",
            "state": "APPROVED",
        }
    )

    assert operation.workspace_id == workspace_id
    assert operation.state is DeletionOperationState.APPROVED


def test_supabase_row_adapter_rejects_malformed_state() -> None:
    from researchos.saas.retention_reconciliation import _operation_from_row

    with pytest.raises(RuntimeError):
        _operation_from_row(
            {
                "workspace_id": str(uuid4()),
                "operation_id": "delete-1",
                "resource_type": "artifact",
                "resource_id": "artifact-1",
                "state": "UNKNOWN",
            }
        )
