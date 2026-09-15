from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from scripts.discover_xauusd_m1_nested_edges import Candidate, run


def _event(index: int, *, label: bool, session: str, realized_lag_hours: int = 1) -> dict:
    timestamp = datetime(2021, 1, 1, tzinfo=timezone.utc) + timedelta(hours=index)
    realized_end = timestamp + timedelta(hours=realized_lag_hours)
    return {
        "event_id": f"E{index:04d}",
        "timestamp": timestamp.isoformat(),
        "direction": "bullish" if index % 2 == 0 else "bearish",
        "context": {
            "market_regime": "Ranging",
            "volatility_state": "Low",
            "session": session,
            "day_of_week": timestamp.weekday(),
            "rsi": 50.0,
            "preceding_return_1d": 0.01,
            "preceding_return_3d": 0.01,
            "preceding_return_5d": 0.01,
            "macd_histogram": 0.01,
            "atr": 1.0,
            "tick_volume": 1000,
        },
        "outcome": {
            "hit_threshold_1d": label,
            "data_availability": {"realized_end_1d": realized_end.isoformat()},
        },
    }


def test_nested_discovery_is_deterministic_and_uses_outer_oos(tmp_path):
    events = []
    for index in range(40):
        session = "Asian" if index % 2 == 0 else "US"
        label = session == "Asian"
        events.append(_event(index, label=label, session=session))
    source = tmp_path / "source.json"
    output_a = tmp_path / "a.json"
    output_b = tmp_path / "b.json"
    source.write_text(
        json.dumps(
            {
                "contract": {"asset": "XAUUSD", "timeframe": "M1"},
                "events_data": events,
            }
        ),
        encoding="utf-8",
    )

    first = run(source, output_a, 20, 10, 10, 2, 1000)
    second = run(source, output_b, 20, 10, 10, 2, 1000)

    assert first == second
    assert first["configuration"]["outer_labels_used_for_selection"] is False
    assert first["selected_oos_events"] > 0


def test_temporal_embargo_excludes_unrealized_training_events(tmp_path):
    events = []
    for index in range(40):
        lag = 100 if index == 19 else 1
        events.append(_event(index, label=index % 2 == 0, session="Asian", realized_lag_hours=lag))
    source = tmp_path / "source.json"
    output = tmp_path / "result.json"
    source.write_text(
        json.dumps(
            {
                "contract": {"asset": "XAUUSD", "timeframe": "M1"},
                "events_data": events,
            }
        ),
        encoding="utf-8",
    )

    result = run(source, output, 20, 10, 10, 2, 1000)

    assert result["folds"][0]["train_end"] != events[19]["timestamp"]


def test_outer_support_failure_is_recorded_not_hard_failure(tmp_path, monkeypatch):
    events = [
        _event(index, label=index % 2 == 0, session="Asian" if index < 30 else "US")
        for index in range(40)
    ]
    source = tmp_path / "source.json"
    output = tmp_path / "result.json"
    source.write_text(
        json.dumps(
            {
                "contract": {"asset": "XAUUSD", "timeframe": "M1"},
                "events_data": events,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "scripts.discover_xauusd_m1_nested_edges._candidate_library",
        lambda contexts: [
            Candidate("session=Asian", lambda context: context.get("session") == "Asian")
        ],
    )

    result = run(source, output, 20, 10, 10, 5, 1000)

    assert result["fold_count"] == 2
    assert result["outer_support_failures"] >= 1
    assert result["folds"][0]["outer_support_met"] is True
    assert result["folds"][1]["outer_support_met"] is False
    assert result["folds"][1]["brier_improvement"] is None
    assert result["scientific_gate"]["status"] == "NO_EDGE_OR_INCONCLUSIVE"
