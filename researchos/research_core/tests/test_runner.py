from __future__ import annotations

import hashlib

import pytest

from researchos.research_core.contracts import FROZEN_XAUUSD_M1_WORKFLOW, ResearchDataset, ResearchRequest
from researchos.research_core.runner import FrozenXauusdM1Runner, PipelineArtifact


def _request() -> ResearchRequest:
    dataset = ResearchDataset.from_content(
        dataset_id="fixture-xauusd-m1",
        asset="XAUUSD",
        timeframe="M1",
        content=b"fixture-content",
        rows=(
            {"time": "2026-01-01T00:00:00+00:00", "close": 100.0},
            {"time": "2026-01-01T00:01:00+00:00", "close": 100.1},
        ),
    )
    return ResearchRequest(dataset=dataset)


def test_runner_returns_content_addressed_artifacts() -> None:
    artifact_content = b"evidence"

    def pipeline(request: ResearchRequest):
        assert request.dataset.asset == "XAUUSD"
        assert request.dataset.timeframe == "M1"
        return (PipelineArtifact("evidence-1", "evidence.json", artifact_content),)

    result = FrozenXauusdM1Runner(pipeline).run(_request())

    assert result.status == "SUCCEEDED"
    assert result.source_dataset_sha256 == _request().dataset.content_sha256
    assert len(result.artifacts) == 1
    assert result.artifacts[0].content_sha256 == hashlib.sha256(artifact_content).hexdigest()


def test_runner_converts_pipeline_failure_to_failed_result() -> None:
    def pipeline(request: ResearchRequest):
        raise RuntimeError("pipeline exploded")

    result = FrozenXauusdM1Runner(pipeline).run(_request())

    assert result.status == "FAILED"
    assert result.source_dataset_sha256 == _request().dataset.content_sha256
    assert result.artifacts == ()
    assert result.failures == ("RuntimeError: pipeline exploded",)


def test_runner_rejects_wrong_workflow_before_pipeline_execution() -> None:
    called = False

    def pipeline(request: ResearchRequest):
        nonlocal called
        called = True
        return ()

    request = ResearchRequest(dataset=_request().dataset)
    object.__setattr__(request, "workflow_id", "wrong-workflow")

    with pytest.raises(ValueError, match="unsupported workflow_id"):
        FrozenXauusdM1Runner(pipeline).run(request)

    assert called is False


def test_frozen_workflow_id_is_stable() -> None:
    assert FrozenXauusdM1Runner.workflow_id == FROZEN_XAUUSD_M1_WORKFLOW
