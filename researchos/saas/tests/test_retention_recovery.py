from uuid import uuid4

import pytest

from researchos.saas.retention_reconciliation import (
    DeletionOperation,
    DeletionOperationState,
    InMemoryDeletionOperationStore,
)
from researchos.saas.retention_recovery import complete_reconciliation


def _seed_reconciliation_required() -> tuple[InMemoryDeletionOperationStore, object]:
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
    store.transition(
        workspace_id,
        "delete-artifact-1",
        "artifact",
        "artifact-1",
        DeletionOperationState.RECONCILIATION_REQUIRED,
    )
    return store, workspace_id


def test_complete_reconciliation_closes_existing_reconciliation() -> None:
    store, workspace_id = _seed_reconciliation_required()

    operation = complete_reconciliation(
        store=store,
        workspace_id=workspace_id,
        operation_id="delete-artifact-1",
        resource_type="artifact",
        resource_id="artifact-1",
    )

    assert operation.state is DeletionOperationState.COMPLETED
    assert store.get(workspace_id, "delete-artifact-1") == operation


def test_complete_reconciliation_requires_existing_operation() -> None:
    with pytest.raises(KeyError):
        complete_reconciliation(
            store=InMemoryDeletionOperationStore(),
            workspace_id=uuid4(),
            operation_id="missing",
            resource_type="artifact",
            resource_id="artifact-1",
        )


def test_complete_reconciliation_rejects_wrong_resource_identity() -> None:
    store, workspace_id = _seed_reconciliation_required()

    with pytest.raises(ValueError, match="resource identity"):
        complete_reconciliation(
            store=store,
            workspace_id=workspace_id,
            operation_id="delete-artifact-1",
            resource_type="artifact",
            resource_id="other-artifact",
        )


def test_completed_operation_is_terminal() -> None:
    store, workspace_id = _seed_reconciliation_required()
    complete_reconciliation(
        store=store,
        workspace_id=workspace_id,
        operation_id="delete-artifact-1",
        resource_type="artifact",
        resource_id="artifact-1",
    )

    with pytest.raises(ValueError, match="invalid deletion operation transition"):
        store.transition(
            workspace_id,
            "delete-artifact-1",
            "artifact",
            "artifact-1",
            DeletionOperationState.DELETE_ATTEMPTED,
        )
