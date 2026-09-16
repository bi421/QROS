"""Tests that forward-day outcomes use timestamps rather than row offsets."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from researchos.market_memory.event_schema import EventContext, MarketEvent
from researchos.market_memory.outcome_engine import compute_forward_outcomes


def _event(ts: datetime, timeframe: str) -> MarketEvent:
    context = EventContext(event_id="e", asset="XAUUSD", timeframe=timeframe, timestamp=ts)
    return MarketEvent(
        event_id="e",
        asset="XAUUSD",
        timeframe=timeframe,
        event_type="sma_crossover",
        direction="bullish",
        timestamp=ts,
        event_price=100.0,
        context=context,
    )


def test_m1_one_day_horizon_is_not_one_bar():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(24 * 60 + 1):
        ts = start + timedelta(minutes=i)
        rows.append((ts, 100.0, 100.0, 100.0, 100.0 + (1.0 if i == 1440 else 0.0)))
    df = pl.DataFrame(rows, schema=["timestamp", "open", "high", "low", "close"], orient="row")
    result = compute_forward_outcomes([_event(start, "M1")], df)
    assert result[0].outcome is not None
    assert result[0].outcome.return_1d == pytest.approx(0.01)


def test_unsupported_timeframe_fails_closed():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    df = pl.DataFrame(
        {
            "timestamp": [start, start + timedelta(days=1)],
            "open": [100.0, 100.0],
            "high": [100.0, 101.0],
            "low": [100.0, 100.0],
            "close": [100.0, 101.0],
        }
    )
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        compute_forward_outcomes([_event(start, "UNKNOWN")], df)
