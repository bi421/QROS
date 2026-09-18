"""Boundary tests for the application-independent scientific contracts."""

import pytest

from researchos.research_core import (
    FROZEN_XAUUSD_M1_WORKFLOW,
    ResearchArtifact,
    ResearchDataset,
    ResearchRequest,
    ResearchResult,
)

SHA256 = "a" * 64


def _dataset(**overrides):
    values = {
        "dataset_id": "dataset-1",
        "asset": "XAUUSD",
        "timeframe": "M1",
        "content": b"time,open,high,low,close\n1,1,2,0,1\n",
        "rows": ({"time": "1", "open": 1, "high": 2, "low": 0, "close": 1},),
    }
    values.update(overrides)
    return ResearchDataset.from_content(**values)


def test_frozen_workflow_accepts_xauusd_m1_dataset():
    request = ResearchRequest(dataset=_dataset())

    assert request.workflow_id == FROZEN_XAUUSD_M1_WORKFLOW
    assert len(request.dataset.content_sha256) == 64
    assert request.dataset.provenance.row_count == 1


def test_workflow_rejects_non_frozen_workflow():
    with pytest.raises(ValueError, match="unsupported workflow_id"):
        ResearchRequest(dataset=_dataset(), workflow_id="experimental")


def test_workflow_rejects_non_xauusd_dataset():
    with pytest.raises(ValueError, match="XAUUSD"):
        ResearchRequest(dataset=_dataset(asset="BTCUSDT"))


def test_dataset_provenance_is_derived_from_content_and_rows():
    dataset = _dataset()
    assert dataset.content_sha256 != SHA256
    assert len(dataset.provenance.rows_sha256) == 64
    assert dataset.provenance.row_count == len(dataset.rows)


def test_dataset_rejects_tampered_rows_against_provenance():
    dataset = _dataset()
    with pytest.raises(ValueError, match="rows do not match"):
        ResearchDataset(
            dataset_id=dataset.dataset_id,
            asset=dataset.asset,
            timeframe=dataset.timeframe,
            provenance=dataset.provenance,
            rows=({"time": "tampered"},),
        )


def test_dataset_provenance_is_stable_for_same_content_and_rows():
    first = _dataset()
    second = _dataset()
    assert first.content_sha256 == second.content_sha256
    assert first.provenance.rows_sha256 == second.provenance.rows_sha256


def test_dataset_content_identity_changes_when_uploaded_bytes_change():
    first = _dataset()
    second = _dataset(content=b"different-bytes", rows=())
    assert first.content_sha256 != second.content_sha256


def test_dataset_requires_nonnegative_row_count():
    with pytest.raises(ValueError, match="row_count"):
        from researchos.research_core.contracts import DatasetProvenance

        DatasetProvenance(SHA256, SHA256, -1)


def test_result_requires_valid_status_and_source_identity():
    artifact = ResearchArtifact("artifact-1", "evidence", SHA256)
    result = ResearchResult("SUCCEEDED", SHA256, (artifact,))

    assert result.status == "SUCCEEDED"
    assert result.artifacts == (artifact,)


def test_successful_result_cannot_hide_failures():
    with pytest.raises(ValueError, match="failures"):
        ResearchResult("SUCCEEDED", SHA256, failures=("failure",))
