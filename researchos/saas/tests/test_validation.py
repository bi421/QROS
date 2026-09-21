from uuid import uuid4

import pytest

from researchos.saas.validation import ResearchValidationRecord


def test_validation_record_requires_matching_claim_plan_pair() -> None:
    with pytest.raises(ValueError, match="claim_id and plan_hash"):
        ResearchValidationRecord(
            id=uuid4(),
            workspace_id=uuid4(),
            research_run_id=uuid4(),
            result_manifest_sha256="a" * 64,
            claim_id="claim-1",
            plan_hash=None,
            validation_sha256="b" * 64,
            status="validated",
            metrics={"accuracy": 0.5},
        )


def test_validation_record_is_immutable_and_hashes_canonical_payload() -> None:
    payload_a = {"metric": 0.5, "folds": [1, 2], "nested": {"b": 2, "a": 1}}
    payload_b = {"nested": {"a": 1, "b": 2}, "folds": [1, 2], "metric": 0.5}
    assert ResearchValidationRecord.compute_validation_sha256(payload_a) == ResearchValidationRecord.compute_validation_sha256(payload_b)

    record = ResearchValidationRecord(
        id=uuid4(),
        workspace_id=uuid4(),
        research_run_id=uuid4(),
        result_manifest_sha256="a" * 64,
        claim_id="claim-1",
        plan_hash="c" * 64,
        validation_sha256=ResearchValidationRecord.compute_validation_sha256(payload_a),
        status="validated",
        metrics={"accuracy": 0.5},
    )
    with pytest.raises(AttributeError):
        record.status = "rejected"


def test_validation_record_rejects_invalid_hashes_and_contract_versions() -> None:
    base = dict(
        id=uuid4(),
        workspace_id=uuid4(),
        research_run_id=uuid4(),
        result_manifest_sha256="a" * 64,
        claim_id=None,
        plan_hash=None,
        validation_sha256="b" * 64,
        status="validated",
        metrics={},
    )
    with pytest.raises(ValueError):
        ResearchValidationRecord(**{**base, "result_manifest_sha256": "bad"})
    with pytest.raises(ValueError, match="unsupported validation contract"):
        ResearchValidationRecord(**{**base, "contract_version": "9.9.9"})
