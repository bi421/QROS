from uuid import uuid4

import pytest

from researchos.saas.finding import ResearchFindingRecord, VALIDATED_STATUS
from researchos.saas.finding_api import InMemoryResearchFindingStore


def _record(payload: dict[str, object] | None = None) -> ResearchFindingRecord:
    body = payload or {"finding": "deterministic validation outcome", "metrics": {"brier_improvement": 0.1}}
    return ResearchFindingRecord(
        id=uuid4(),
        workspace_id=uuid4(),
        research_run_id=uuid4(),
        validation_id=uuid4(),
        result_manifest_sha256="a" * 64,
        validation_sha256="b" * 64,
        claim_id="claim-1",
        plan_hash="c" * 64,
        finding_sha256=ResearchFindingRecord.compute_finding_sha256(body),
        status=VALIDATED_STATUS,
        payload=body,
    )


def test_finding_record_is_immutable_and_canonical() -> None:
    record = _record({"z": 1, "a": {"b": 2, "a": 1}})
    assert record.finding_sha256 == ResearchFindingRecord.compute_finding_sha256({"a": {"a": 1, "b": 2}, "z": 1})
    with pytest.raises(Exception):
        record.status = "REJECTED"  # type: ignore[misc]


def test_finding_store_is_tenant_scoped_and_idempotent() -> None:
    store = InMemoryResearchFindingStore()
    record = _record()
    assert store.create(record) == record
    assert store.create(record) == record
    assert store.get(record.workspace_id, record.research_run_id) == record
    assert store.get(uuid4(), record.research_run_id) is None


def test_finding_store_rejects_digest_conflict() -> None:
    store = InMemoryResearchFindingStore()
    record = _record()
    store.create(record)
    conflicting = _record({"finding": "different"})
    conflicting = ResearchFindingRecord(
        id=conflicting.id,
        workspace_id=record.workspace_id,
        research_run_id=record.research_run_id,
        validation_id=record.validation_id,
        result_manifest_sha256=record.result_manifest_sha256,
        validation_sha256=record.validation_sha256,
        claim_id=record.claim_id,
        plan_hash=record.plan_hash,
        finding_sha256=conflicting.finding_sha256,
        status=VALIDATED_STATUS,
        payload=conflicting.payload,
    )
    with pytest.raises(ValueError, match="different digest"):
        store.create(conflicting)


def test_finding_record_rejects_non_validated_status() -> None:
    body = {"finding": "not certified"}
    with pytest.raises(ValueError, match="VALIDATED"):
        ResearchFindingRecord(
            id=uuid4(), workspace_id=uuid4(), research_run_id=uuid4(),
            validation_id=uuid4(), result_manifest_sha256="a"*64,
            validation_sha256="b"*64, claim_id=None, plan_hash=None,
            finding_sha256=ResearchFindingRecord.compute_finding_sha256(body),
            status="INCONCLUSIVE", payload=body,
        )
