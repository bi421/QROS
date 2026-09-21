from __future__ import annotations

import pytest

from researchos.market_memory.evidence import create_evidence_record
from researchos.research_identity import DatasetIdentity


def _kwargs() -> dict[str, object]:
    return {
        "finding_name": "bullish_crossover",
        "dataset_id": "xauusd-d1",
        "dataset_version": "version-1",
        "event_definition": "SMA20/100 crossover",
        "condition_definition": "bullish",
        "sample_size": 100,
        "time_range": ("2021-01-01T00:00:00+00:00", "2021-12-31T00:00:00+00:00"),
        "computation_method": "forward_return_analysis",
        "code_module": "test",
        "statistical_method": "wilson",
        "result": {"probability": 0.55},
    }


def test_validated_evidence_can_bind_exact_dataset_identity() -> None:
    identity = DatasetIdentity("xauusd-d1", "content-a", "dataset-a")
    record = create_evidence_record(
        **_kwargs(),
        dataset_identity=identity,
        dataset_content_hash="content-a",
        dataset_hash="dataset-a",
    )
    assert record.uncertainty["provenance"]["dataset_identity"] == identity.to_dict()


def test_evidence_rejects_dataset_content_mismatch() -> None:
    identity = DatasetIdentity("xauusd-d1", "content-a", "dataset-a")
    with pytest.raises(ValueError, match="dataset identity mismatch"):
        create_evidence_record(
            **_kwargs(),
            dataset_identity=identity,
            dataset_content_hash="content-b",
            dataset_hash="dataset-a",
        )


def test_evidence_requires_both_hashes_for_strict_binding() -> None:
    identity = DatasetIdentity("xauusd-d1", "content-a", "dataset-a")
    with pytest.raises(ValueError, match="dataset_content_hash and dataset_hash"):
        create_evidence_record(
            **_kwargs(),
            dataset_identity=identity,
            dataset_content_hash="content-a",
        )


def test_exact_dataset_identity_changes_provenance_digest() -> None:
    identity = DatasetIdentity("xauusd-d1", "content-a", "dataset-a")
    first = create_evidence_record(
        **_kwargs(),
        dataset_identity=identity,
        dataset_content_hash="content-a",
        dataset_hash="dataset-a",
    )
    second = create_evidence_record(
        **_kwargs(),
        dataset_identity=DatasetIdentity("xauusd-d1", "content-b", "dataset-a"),
        dataset_content_hash="content-b",
        dataset_hash="dataset-a",
    )
    assert (
        first.uncertainty["provenance"]["evidence_computation_digest"]
        != second.uncertainty["provenance"]["evidence_computation_digest"]
    )


def test_exact_dataset_hash_changes_provenance_digest() -> None:
    first = create_evidence_record(
        **_kwargs(),
        dataset_identity=DatasetIdentity("xauusd-d1", "content-a", "dataset-a"),
        dataset_content_hash="content-a",
        dataset_hash="dataset-a",
    )
    second = create_evidence_record(
        **_kwargs(),
        dataset_identity=DatasetIdentity("xauusd-d1", "content-a", "dataset-b"),
        dataset_content_hash="content-a",
        dataset_hash="dataset-b",
    )
    assert (
        first.uncertainty["provenance"]["evidence_computation_digest"]
        != second.uncertainty["provenance"]["evidence_computation_digest"]
    )
