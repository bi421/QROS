from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts._confirm_xauusd_m1_frozen_candidate_impl import (
    _evaluate_fold,
    _select_frozen_candidate,
)
from scripts.confirm_xauusd_m1_frozen_candidate import run


def _event(index: int, label: bool, *, session: str = "US", direction: str = "bullish") -> dict:
    timestamp = datetime(2021, 1, 1, tzinfo=timezone.utc) + timedelta(hours=index)
    return {
        "event_id": f"E{index:05d}",
        "timestamp": timestamp.isoformat(),
        "direction": direction,
        "context": {
            "market_regime": "Trending",
            "volatility_state": "Low",
            "session": session,
            "day_of_week": timestamp.weekday(),
            "rsi": 60.0 if session == "US" else 40.0,
            "preceding_return_1d": 0.01,
            "preceding_return_3d": 0.01,
            "preceding_return_5d": 0.01,
            "macd_histogram": 0.01,
            "atr": 1.0,
            "tick_volume": 1000,
        },
        "outcome": {
            "hit_threshold_1d": label,
            "data_availability": {
                "realized_end_1d": (timestamp + timedelta(hours=1)).isoformat()
            },
        },
    }


def test_candidate_is_selected_from_development_only() -> None:
    development = [
        _event(i, label=(i % 2 == 0), session="US" if i % 2 == 0 else "Asian")
        for i in range(120)
    ]
    candidate, selection = _select_frozen_candidate(development, 10, 8)
    assert candidate.name
    assert selection["development_selection_used_confirmation_labels"] is False


def test_frozen_candidate_evaluation_does_not_change_candidate_definition() -> None:
    development = [
        _event(i, label=(i % 2 == 0), session="US" if i % 2 == 0 else "Asian")
        for i in range(120)
    ]
    candidate, _ = _select_frozen_candidate(development, 10, 8)
    confirmation = [
        _event(i + 120, label=(i % 3 == 0), session="US" if i % 2 == 0 else "Asian")
        for i in range(50)
    ]
    before = candidate.name
    result = _evaluate_fold(confirmation, candidate, development)
    assert candidate.name == before
    assert result["events"] == 50
    assert result["candidate_events"] >= 0


def test_confirmation_period_must_have_b_level_support(tmp_path) -> None:
    events = [
        _event(i, label=(i % 2 == 0), session="US" if i % 2 == 0 else "Asian")
        for i in range(500)
    ]
    source = tmp_path / "source.json"
    output = tmp_path / "result.json"
    import json

    source.write_text(
        json.dumps(
            {
                "contract": {"asset": "XAUUSD", "timeframe": "M1"},
                "events_data": events,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="B-level requires 10000"):
        run(source, output, "2021-01-06T00:00:00+00:00", "2021-01-10T00:00:00+00:00", 10, 250, 8)
