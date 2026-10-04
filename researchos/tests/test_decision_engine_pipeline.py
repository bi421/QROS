"""End-to-end tests for the completed Decision Intelligence Engine pipeline."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from researchos.decision_engine.context import DecisionContext
from researchos.decision_engine.pipeline import DecisionPipeline, DecisionPipelineError

FIXED_TS = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)


def _without_runtime_timestamps(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_runtime_timestamps(item)
            for key, item in value.items()
            if key not in {"created_at", "timestamp"}
        }
    if isinstance(value, list):
        return [_without_runtime_timestamps(item) for item in value]
    return value


def make_context(**overrides: object) -> DecisionContext:
    params: dict[str, object] = {
        "asset": "XAUUSD",
        "market_snapshot_id": "snap_001",
        "market_regime_id": "regime_001",
        "macro_state_id": "macro_001",
        "historical_scenario_ids": ["hist_001", "hist_002"],
        "experiment_result_ids": ["exp_001"],
        "validation_ids": ["val_001"],
        "research_ids": ["res_001"],
        "market_memory_report_ids": ["mmr_001"],
        "simulation_result_ids": ["sim_001"],
        "timeframe": "1h",
        "decision_timestamp": FIXED_TS,
        "ontology_tags": ["gold", "decision_engine"],
    }
    params.update(overrides)
    return DecisionContext(**params)


def test_pipeline_executes_every_stage_and_preserves_provenance() -> None:
    result = DecisionPipeline().run(make_context())
    assert result.context.asset == "XAUUSD"
    assert result.evidence.decision_context_id == result.context.id
    assert result.score.context_id == result.context.id
    assert result.probability.decision_context_id == result.context.id
    assert result.report.context_id == result.context.id
    assert result.report.score_id == result.score.id
    assert result.report.probability_id == result.probability.id
    assert result.report.reasoning_steps
    assert result.report_hash == result.report.report_hash


def test_pipeline_is_deterministic_for_fixed_context() -> None:
    context = make_context()
    first = DecisionPipeline().run(context)
    second = DecisionPipeline().run(context)
    assert first.evidence.collection_hash == second.evidence.collection_hash
    assert first.score.score_hash == second.score.score_hash
    assert first.probability.assessment_hash == second.probability.assessment_hash
    assert first.report.report_hash == second.report.report_hash
    assert _without_runtime_timestamps(first.report.to_dict()) == _without_runtime_timestamps(second.report.to_dict())


def test_pipeline_fails_closed_before_report_on_invalid_context() -> None:
    with pytest.raises(DecisionPipelineError, match="DecisionContext validation failed"):
        DecisionPipeline().run(make_context(asset=""))


def test_pipeline_handles_empty_evidence_without_fabricating_direction() -> None:
    result = DecisionPipeline().run(
        make_context(
            market_snapshot_id="",
            market_regime_id="",
            macro_state_id="",
            historical_scenario_ids=[],
            experiment_result_ids=[],
            validation_ids=[],
            research_ids=[],
            market_memory_report_ids=[],
            simulation_result_ids=[],
            ontology_tags=[],
        )
    )
    assert result.evidence.total_items == 0
    assert result.probability.bullish_probability == pytest.approx(1 / 3)
    assert result.probability.bearish_probability == pytest.approx(1 / 3)
    assert result.probability.neutral_probability == pytest.approx(1 / 3)
    assert "No evidence items available for probability assessment" in result.probability.limitations


def test_pipeline_runs_independent_contexts_in_declared_order() -> None:
    contexts = (
        make_context(market_snapshot_id="snap_a"),
        make_context(market_snapshot_id="snap_b"),
        make_context(market_snapshot_id="snap_c"),
    )
    results = DecisionPipeline().run_many(contexts)

    assert tuple(result.context.market_snapshot_id for result in results) == (
        "snap_a",
        "snap_b",
        "snap_c",
    )
    assert all(result.report.reasoning_steps for result in results)


def test_pipeline_run_many_rejects_empty_input() -> None:
    with pytest.raises(DecisionPipelineError, match="at least one DecisionContext"):
        DecisionPipeline().run_many(())
