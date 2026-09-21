from uuid import uuid4

import pytest

from researchos.saas.validation import ResearchValidationRecord
from researchos.saas.validation_api import InMemoryResearchValidationStore


def _record() -> ResearchValidationRecord:
    payload = {"metrics": {"brier_improvement": 0.1}, "gate": "PASS"}
    return ResearchValidationRecord(
        id=uuid4(),
        workspace_id=uuid4(),
        research_run_id=uuid4(),
        result_manifest_sha256="a" * 64,
        claim_id="claim-1",
        plan_hash="b" * 64,
        validation_sha256=ResearchValidationRecord.compute_validation_sha256(payload),
        status="validated",
        metrics={"brier_improvement": 0.1},
    )


def test_validation_store_is_tenant_scoped_and_idempotent() -> None:
    store = InMemoryResearchValidationStore()
    record = _record()
    assert store.create(record) == record
    assert store.create(record) == record
    assert store.get(record.workspace_id, record.research_run_id) == record
    assert store.get(uuid4(), record.research_run_id) is None


def test_validation_store_rejects_digest_conflict() -> None:
    store = InMemoryResearchValidationStore()
    record = _record()
    store.create(record)
    conflicting = ResearchValidationRecord(
        id=uuid4(),
        workspace_id=record.workspace_id,
        research_run_id=record.research_run_id,
        result_manifest_sha256=record.result_manifest_sha256,
        claim_id=record.claim_id,
        plan_hash=record.plan_hash,
        validation_sha256="c" * 64,
        status="rejected",
        metrics={},
    )
    with pytest.raises(ValueError, match="different digest"):
        store.create(conflicting)
