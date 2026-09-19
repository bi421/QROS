from uuid import uuid4

from researchos.saas.retention_reconciliation import (
    DeletionOperation,
    DeletionOperationState,
    InMemoryDeletionOperationStore,
    require_reconciliation_after_delete,
)


def test_reconciliation_state_is_durable_in_operation_store() -> None:
    store = InMemoryDeletionOperationStore()
    workspace_id = uuid4()

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
        try:
            DeletionOperation(
                workspace_id=workspace_id,
                operation_id=operation_id,
                resource_type=resource_type,
                resource_id=resource_id,
                state=DeletionOperationState.APPROVED,
            )
        except ValueError:
            continue
        raise AssertionError("invalid deletion operation identity was accepted")
