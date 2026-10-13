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
    with pytest.raises(ValueError, match=r"exactly -1, 0, or \+1"):
        QROSPipelineEvaluator().ingest(pl.DataFrame({"state": [1.5], "close": [10.0]}))
    with pytest.raises(ValueError, match="strictly positive"):
        QROSPipelineEvaluator().ingest(pl.DataFrame({"state": [1], "close": [0.0]}))


def test_dashboard_discloses_scope() -> None:
    evaluator = QROSPipelineEvaluator().ingest(pl.DataFrame({"state": [0, 1, -1], "close": [10.0, 11.0, 10.0]}))
    dashboard = evaluator.dashboard()
    assert "not upstream live-stream throughput" in dashboard
    assert "No alpha claim" in dashboard

def test_fail_closed_on_null_or_invalid_safety_trigger() -> None:
    with pytest.raises(ValueError, match="safety_gate_triggered must not contain null"):
        QROSPipelineEvaluator().ingest(pl.DataFrame({
            "state": [0, 1],
            "close": [10.0, 11.0],
            "safety_gate_triggered": [False, None],
        })).compute()

    with pytest.raises(ValueError, match="only boolean or numeric 0/1"):
        QROSPipelineEvaluator().ingest(pl.DataFrame({
            "state": [0, 1],
            "close": [10.0, 11.0],
            "safety_gate_triggered": [0, 2],
        })).compute()

    with pytest.raises(ValueError, match="safety_passed must contain only boolean or numeric 0/1"):
        QROSPipelineEvaluator().ingest(pl.DataFrame({
            "state": [0, 1],
            "close": [10.0, 11.0],
            "safety_passed": [1, 2],
        })).compute()

def test_safety_regime_diagnostics_handle_horizon_longer_than_stream() -> None:
    frame = pl.DataFrame({
        "state": [1, 0, -1],
        "close": [100.0, 101.0, 99.0],
        "safety_gate_triggered": [True, False, True],
    })
    metrics = QROSPipelineEvaluator(EvaluationConfig(horizons=(1, 5))).ingest(frame).compute()
    long_horizon = metrics["safety_regime_forward_diagnostics"]["5"]
    assert long_horizon["safety_locked"]["count"] == 0
    assert long_horizon["safety_locked"]["mean_absolute_forward_return"] is None
    assert long_horizon["not_locked"]["count"] == 0
    assert metrics["forward_returns"]["5"]["evaluated_signals"] == 0
