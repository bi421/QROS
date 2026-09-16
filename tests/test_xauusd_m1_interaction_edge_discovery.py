from __future__ import annotations

import json
import math
import random
import statistics
import pytest
from datetime import datetime, timedelta, timezone

from scripts.discover_xauusd_m1_interaction_edges import run, _probability, _brier


def _event(index: int, *, label: bool, session: str, regime: str) -> dict:
    timestamp = datetime(2021, 1, 1, tzinfo=timezone.utc) + timedelta(hours=index)
    return {
        "event_id": f"E{index:04d}",
        "timestamp": timestamp.isoformat(),
        "direction": "bullish" if index % 2 == 0 else "bearish",
        "context": {
            "market_regime": regime,
            "volatility_state": "Low",
            "session": session,
            "day_of_week": timestamp.weekday(),
            "rsi": 40.0 if session == "Asian" else 60.0,
            "preceding_return_1d": 0.01 if regime == "Trending" else -0.01,
            "preceding_return_3d": 0.01,
            "preceding_return_5d": 0.01,
            "macd_histogram": 0.01 if session == "Asian" else -0.01,
            "atr": 1.0,
            "tick_volume": 1000,
        },
        "outcome": {
            "hit_threshold_1d": label,
            "data_availability": {"realized_end_1d": (timestamp + timedelta(hours=1)).isoformat()},
        },
    }


def test_interaction_discovery_is_deterministic_and_leakage_safe(tmp_path):
    events = []
    for index in range(80):
        session = "Asian" if index % 2 == 0 else "US"
        regime = "Trending" if index % 4 < 2 else "Ranging"
        label = session == "Asian" and regime == "Trending"
        events.append(_event(index, label=label, session=session, regime=regime))
    source = tmp_path / "source.json"
    output_a = tmp_path / "a.json"
    output_b = tmp_path / "b.json"
    source.write_text(
        json.dumps({"contract": {"asset": "XAUUSD", "timeframe": "M1"}, "events_data": events}),
        encoding="utf-8",
    )
    first = run(source, output_a, 40, 20, 20, 5, 8)
    second = run(source, output_b, 40, 20, 20, 5, 8)
    assert first == second
    assert first["configuration"]["outer_labels_used_for_selection"] is False
    assert first["fold_count"] == 2
    assert first["evaluated_fold_count"] > 0
    assert any(fold["candidate_kind"] == "interaction" for fold in first["folds"])


def test_outer_support_failure_is_recorded(tmp_path):
    events = []
    for index in range(60):
        session = "Asian" if index < 30 else "US"
        events.append(_event(index, label=index % 2 == 0, session=session, regime="Trending"))
    source = tmp_path / "source.json"
    output = tmp_path / "result.json"
    source.write_text(
        json.dumps({"contract": {"asset": "XAUUSD", "timeframe": "M1"}, "events_data": events}),
        encoding="utf-8",
    )
    result = run(source, output, 40, 10, 10, 12, 8)
    assert result["fold_count"] == 2
    assert result["outer_support_failures"] >= 1
    assert result["scientific_gate"]["status"] == "NO_EDGE_OR_INCONCLUSIVE"


# ==============================================================================
# DEEP VALIDATION TESTS: Numerical Stability, Statistical Correctness, Edge Cases
# ==============================================================================


def test_probability_jeffreys_smoothing_bounds():
    rows_true = [{"outcome": {"hit_threshold_1d": True}} for _ in range(100)]
    assert 0.0 < _probability(rows_true) < 1.0
    rows_false = [{"outcome": {"hit_threshold_1d": False}} for _ in range(100)]
    assert 0.0 < _probability(rows_false) < 1.0


def test_brier_score_large_sample_numerical_stability():
    rows = [{"outcome": {"hit_threshold_1d": True}} for _ in range(10**5)]
    brier = _brier(0.5, rows)
    assert math.isfinite(brier) and 0.0 <= brier <= 1.0


def test_brier_score_extreme_probability_stability():
    rows = [{"outcome": {"hit_threshold_1d": False}} for _ in range(100)]
    brier = _brier(1e-10, rows)
    assert math.isfinite(brier) and brier > 0.0


def test_brier_score_statistical_unbiasedness():
    true_p, target = 0.7, 0.21
    scores = []
    for _ in range(500):
        sample = [{"outcome": {"hit_threshold_1d": random.random() < true_p}} for _ in range(1000)]
        scores.append(_brier(_probability(sample), sample))
    assert abs(statistics.mean(scores) - target) < 0.05


def test_insufficient_events_raises_value_error(tmp_path):
    events = [
        {
            "event_id": f"E{i:04d}",
            "timestamp": f"2021-01-01T0{i}:00:00+00:00",
            "outcome": {
                "hit_threshold_1d": True,
                "data_availability": {"realized_end_1d": "2021-01-01T00:00:00+00:00"},
            },
        }
        for i in range(5)
    ]
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps({"contract": {"asset": "XAUUSD", "timeframe": "M1"}, "events_data": events}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="insufficient complete events"):
        run(source, tmp_path / "out.json", 40, 20, 20, 5, 8)
