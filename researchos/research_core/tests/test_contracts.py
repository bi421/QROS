"""Boundary tests for the application-independent scientific contracts."""

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
        "content_sha256": SHA256,
        "rows": (),
    }
    values.update(overrides)
    return ResearchDataset(**values)


def test_frozen_workflow_accepts_xauusd_m1_dataset():
    request = ResearchRequest(dataset=_dataset())

    assert request.workflow_id == FROZEN_XAUUSD_M1_WORKFLOW
    assert request.dataset.content_sha256 == SHA256


def test_workflow_rejects_non_frozen_workflow():
    try:
        ResearchRequest(dataset=_dataset(), workflow_id="experimental")
    except ValueError as exc:
        assert "unsupported workflow_id" in str(exc)
    else:
        raise AssertionError("non-frozen workflow was accepted")


def test_workflow_rejects_non_xauusd_dataset():
    try:
        ResearchRequest(dataset=_dataset(asset="BTCUSDT"))
    except ValueError as exc:
        assert "XAUUSD" in str(exc)
    else:
        raise AssertionError("non-XAUUSD dataset was accepted")


def test_dataset_requires_valid_sha256():
    try:
        _dataset(content_sha256="not-a-sha256")
    except ValueError as exc:
        assert "SHA-256" in str(exc)
    else:
        raise AssertionError("invalid SHA-256 was accepted")


def test_result_requires_valid_status_and_source_identity():
    artifact = ResearchArtifact("artifact-1", "evidence", SHA256)
    result = ResearchResult("SUCCEEDED", SHA256, (artifact,))

    assert result.status == "SUCCEEDED"
    assert result.artifacts == (artifact,)


def test_successful_result_cannot_hide_failures():
    try:
        ResearchResult("SUCCEEDED", SHA256, failures=("failure",))
    except ValueError as exc:
        assert "failures" in str(exc)
    else:
        raise AssertionError("successful result accepted failures")
