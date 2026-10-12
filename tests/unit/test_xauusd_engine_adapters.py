"""Contract tests for concrete XAUUSD technical and quant-math adapters."""

from datetime import datetime, timedelta, timezone

import pytest

from researchos.orchestration.xauusd_engine_adapters import (
    XAUUSDMarketSnapshot,
    XAUUSDQuantMathEvidenceAdapter,
    XAUUSDTechnicalEvidenceAdapter,
)
from researchos.orchestration.xauusd_research import (
    EngineStatus,
    XAUUSDResearchOrchestrator,
    XAUUSDResearchRequest,
)
from researchos.quant_engine.technical import Bars

NOW = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)
DATASET_VERSION = "dataset-v1"
TIMEFRAME_STEPS = {
    "M15": timedelta(minutes=15),
    "M30": timedelta(minutes=30),
    "H1": timedelta(hours=1),
    "H4": timedelta(hours=4),
    "D1": timedelta(days=1),
}


def make_snapshot(now=NOW, count=80, dataset_version=DATASET_VERSION):
    bars_by_timeframe = {}
    timestamps_by_timeframe = {}
    for timeframe, step in TIMEFRAME_STEPS.items():
        opens = [1800.0 + i * 0.2 for i in range(count)]
        closes = [value + 0.05 + (i % 3) * 0.01 for i, value in enumerate(opens)]
        bars_by_timeframe[timeframe] = Bars(
            open=opens,
            high=[max(o, c) + 0.4 for o, c in zip(opens, closes)],
            low=[min(o, c) - 0.4 for o, c in zip(opens, closes)],
            close=closes,
            volume=[100.0] * count,
        )
        timestamps_by_timeframe[timeframe] = tuple(
            now - step * (count - 1 - i) for i in range(count)
        )
    return XAUUSDMarketSnapshot(
        bars_by_timeframe=bars_by_timeframe,
        bar_close_times_by_timeframe=timestamps_by_timeframe,
        dataset_version=dataset_version,
        source_refs=("synthetic-fixture",),
    )


def make_request(**overrides):
    values = {
        "run_id": "adapter-run-001",
        "instrument": "XAUUSD",
        "decision_time": NOW,
        "dataset_version": DATASET_VERSION,
        "config_version": "xauusd-fusion-v1",
    }
    values.update(overrides)
    return XAUUSDResearchRequest(**values)


def test_technical_adapter_emits_closed_bar_evidence_for_all_five_timeframes():
    result = XAUUSDTechnicalEvidenceAdapter()(make_request(), make_snapshot())
    assert result.status is EngineStatus.OK
    assert len(result.evidence) == 25
    assert {record.timeframe for record in result.evidence} == set(TIMEFRAME_STEPS)
    assert all(record.as_of <= NOW for record in result.evidence)
    assert {record.feature_name for record in result.evidence} == {
        "ema_alignment",
        "rsi_centered",
        "macd_histogram",
        "supertrend_direction",
        "atr_14",
    }
    assert all(record.source_refs[-1] == DATASET_VERSION for record in result.evidence)


def test_quant_math_adapter_emits_deterministic_m15_geometry_and_statistics():
    adapter = XAUUSDQuantMathEvidenceAdapter()
    request = make_request()
    snapshot = make_snapshot()
    first = adapter(request, snapshot)
    second = adapter(request, snapshot)
    assert first.status is EngineStatus.OK
    assert [item.evidence_id for item in first.evidence] == [
        item.evidence_id for item in second.evidence
    ]
    assert {item.timeframe for item in first.evidence} == {"M15"}
    assert {"geometry_slope", "z_score_last", "regression_slope"} == {
        item.feature_name for item in first.evidence
    }


def test_orchestrator_runs_real_technical_and_quant_math_adapters_together():
    request = make_request()
    snapshot = make_snapshot()
    result = XAUUSDResearchOrchestrator(
        {
            "technical": XAUUSDTechnicalEvidenceAdapter(),
            "quant_math": XAUUSDQuantMathEvidenceAdapter(),
        },
        required_engines=("technical", "quant_math"),
    ).run(request, snapshot)
    assert result.status.value == "EVIDENCE_COLLECTED"
    assert len(result.evidence) == 28
    assert result.missing_required_engines == ()
    assert result.to_dict()["probabilities"] is None
    assert result.to_dict()["execution_enabled"] is False


def test_adapters_reject_dataset_version_mismatch():
    request = make_request()
    snapshot = make_snapshot(dataset_version="different-dataset")
    with pytest.raises(ValueError, match="DATASET_VERSION_MISMATCH"):
        XAUUSDTechnicalEvidenceAdapter()(request, snapshot)
    with pytest.raises(ValueError, match="DATASET_VERSION_MISMATCH"):
        XAUUSDQuantMathEvidenceAdapter()(request, snapshot)


def test_adapters_do_not_use_bars_after_the_decision_time():
    request = make_request(decision_time=NOW - timedelta(days=20))
    snapshot = make_snapshot()
    with pytest.raises(ValueError, match="NO_CLOSED_BARS_AS_OF_DECISION"):
        XAUUSDQuantMathEvidenceAdapter()(request, snapshot)


def test_snapshot_rejects_duplicate_close_timestamps():
    snapshot = make_snapshot()
    times = dict(snapshot.bar_close_times_by_timeframe)
    times["M15"] = tuple([*times["M15"][:-1], times["M15"][-2]])
    with pytest.raises(ValueError, match="strictly increasing"):
        XAUUSDMarketSnapshot(
            bars_by_timeframe=snapshot.bars_by_timeframe,
            bar_close_times_by_timeframe=times,
            dataset_version=DATASET_VERSION,
        )
