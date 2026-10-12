from __future__ import annotations

import math
import polars as pl
import pytest

from researchos.engines.quant.python.qros_pipeline_evaluator import EvaluationConfig, QROSPipelineEvaluator


def test_distribution_safety_causes_and_latency_metrics() -> None:
    frame = pl.DataFrame({
        "state": [1, -1, 0, 1, 0],
        "close": [100.0, 101.0, 100.0, 102.0, 101.0],
        "latency_ms": [1.0, 2.0, 3.0, 100.0, 5.0],
        "safety_gate_triggered": [False, False, True, True, False],
        "safety_gate_reason": ["", "", "safety_gate_vxy_exceeded", "safety_gate_latency_exceeded", ""],
    })
    metrics = QROSPipelineEvaluator().ingest(frame).compute()
    assert metrics["decision_distribution"]["counts"] == {"-1": 1, "0": 2, "1": 2}
    assert metrics["safety_gate"]["trigger_count"] == 2
    assert metrics["safety_gate"]["root_causes"]["latency"]["count"] == 1
    assert metrics["safety_gate"]["root_causes"]["vxy"]["count"] == 1
    assert math.isclose(metrics["latency"]["median_ms"], 3.0)
    assert math.isclose(metrics["latency"]["p95_ms"], 81.0)
    assert metrics["safety_regime_forward_diagnostics"]["1"]["safety_locked"]["count"] == 2


def test_forward_return_sign_and_safety_exclusion() -> None:
    frame = pl.DataFrame({
        "state": [1, -1, 0, 1, -1, 0],
        "close": [100.0, 110.0, 100.0, 90.0, 99.0, 100.0],
        "safety_gate_triggered": [False, True, False, False, False, False],
    })
    one = QROSPipelineEvaluator(EvaluationConfig(horizons=(1,))).ingest(frame).compute()["forward_returns"]["1"]
    assert one["evaluated_signals"] == 4
    assert math.isclose(one["win_rate"], 0.75)
    assert one["safety_excluded_signals"] == 1
    assert one["clean_evaluated_signals"] == 3
    assert math.isclose(one["clean_win_rate"], 2 / 3)


def test_fail_closed_on_invalid_state_or_price() -> None:
    with pytest.raises(ValueError, match="state values"):
        QROSPipelineEvaluator().ingest(pl.DataFrame({"state": [2], "close": [10.0]}))
    with pytest.raises(ValueError, match="exactly -1, 0, or +1"):
        QROSPipelineEvaluator().ingest(pl.DataFrame({"state": [1.5], "close": [10.0]}))
    with pytest.raises(ValueError, match="strictly positive"):
        QROSPipelineEvaluator().ingest(pl.DataFrame({"state": [1], "close": [0.0]}))


def test_dashboard_discloses_scope() -> None:
    evaluator = QROSPipelineEvaluator().ingest(pl.DataFrame({"state": [0, 1, -1], "close": [10.0, 11.0, 10.0]}))
    dashboard = evaluator.dashboard()
    assert "not upstream live-stream throughput" in dashboard
    assert "No alpha claim" in dashboard
