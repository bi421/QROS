"""Regression tests for the Data -> Research execution boundary."""

from __future__ import annotations

import inspect

import pytest

from researchos.data_engine.boundary import (
    DATA_BOUNDARY_SCHEMA_VERSION,
    ValidatedDatasetRef,
)
from researchos.data_engine.research_reader import ResearchSeries
from researchos.research_boundary import ResearchInput
from researchos.research_core.provenance import (
    ResearchExecutionResult,
    ResearchExecutor,
    execution_hash,
)


def _input() -> ResearchInput:
    ref = ValidatedDatasetRef(
        schema_version=DATA_BOUNDARY_SCHEMA_VERSION,
        dataset_id="dataset-001",
        dataset_content_hash="content-hash",
        dataset_hash="dataset-hash",
        symbol="XAUUSD",
        timeframe="1d",
        data_type="candle",
        record_count=4,
        validation_quality_score=1.0,
    )
    return ResearchInput(
        schema_version="research-boundary.v1",
        research_id="research-001",
        question="Does the experiment have predictive value?",
        methodology_version="phase51.v1",
        dataset=ref,
    )


class StubResolver:
    def resolve(self, reference):
        assert reference.dataset_id == "dataset-001"
        return ResearchSeries(
            close=(1.0, 2.0, 3.0, 4.0),
            high=(1.1, 2.1, 3.1, 4.1),
            low=(0.9, 1.9, 2.9, 3.9),
            volume=(10.0, 11.0, 12.0, 13.0),
        )


def test_execution_api_requires_research_input() -> None:
    executor = ResearchExecutor(StubResolver())
    with pytest.raises(TypeError, match="ResearchInput"):
        executor.execute(object(), lambda series, config: series)


def test_execution_api_does_not_accept_historical_dataset() -> None:
    signature = inspect.signature(ResearchExecutor.execute)
    annotations = {name: str(parameter.annotation) for name, parameter in signature.parameters.items()}
    assert "HistoricalDataset" not in annotations["research_input"]
    assert annotations["research_input"] != "typing.Any"


def test_execution_preserves_dataset_identity_and_methodology() -> None:
    result = ResearchExecutor(StubResolver()).execute(
        _input(),
        lambda series, config: {"bars": len(series.close), "config": config},
        "phase51-config",
    )

    assert isinstance(result, ResearchExecutionResult)
    assert result.research_id == "research-001"
    assert result.dataset_id == "dataset-001"
    assert result.dataset_content_hash == "content-hash"
    assert result.dataset_hash == "dataset-hash"
    assert result.methodology_version == "phase51.v1"
    assert result.result == {"bars": 4, "config": "phase51-config"}
    assert len(result.execution_hash) == 64
    assert result.verify_integrity()
    assert result.to_dict()["execution_hash"] == result.execution_hash


def test_execution_hash_is_deterministic() -> None:
    payload = {"b": [2, 1], "a": {"value": 3}}
    first = execution_hash(
        research_id="research-001",
        dataset_id="dataset-001",
        dataset_content_hash="content-hash",
        dataset_hash="dataset-hash",
        methodology_version="phase51.v1",
        result=payload,
    )
    second = execution_hash(
        research_id="research-001",
        dataset_id="dataset-001",
        dataset_content_hash="content-hash",
        dataset_hash="dataset-hash",
        methodology_version="phase51.v1",
        result={"a": {"value": 3}, "b": [2, 1]},
    )
    assert first == second
    assert len(first) == 64


def test_execution_hash_changes_when_lineage_changes() -> None:
    base = dict(
        research_id="research-001",
        dataset_id="dataset-001",
        dataset_content_hash="content-hash",
        dataset_hash="dataset-hash",
        methodology_version="phase51.v1",
        result={"value": 1},
    )
    baseline = execution_hash(**base)

    for field in ("dataset_id", "dataset_content_hash", "dataset_hash", "methodology_version", "research_id"):
        changed = dict(base)
        changed[field] = changed[field] + "-changed"
        assert execution_hash(**changed) != baseline


def test_execution_hash_changes_when_result_changes() -> None:
    base = dict(
        research_id="research-001",
        dataset_id="dataset-001",
        dataset_content_hash="content-hash",
        dataset_hash="dataset-hash",
        methodology_version="phase51.v1",
    )
    assert execution_hash(**base, result={"value": 1}) != execution_hash(**base, result={"value": 2})


def test_execution_operation_receives_research_safe_series_only() -> None:
    observed = {}

    def operation(series, _config):
        observed["type"] = type(series)
        return "ok"

    result = ResearchExecutor(StubResolver()).execute(_input(), operation)
    assert result.result == "ok"
    assert observed["type"] is ResearchSeries


def test_research_series_rejects_misaligned_data() -> None:
    with pytest.raises(ValueError, match="equal length"):
        ResearchSeries(close=(1.0,), high=(1.0, 2.0), low=(0.0,), volume=(1.0,))
