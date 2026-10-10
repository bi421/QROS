from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from researchos.market_memory.event_schema import EventContext, MarketEvent
from researchos.market_memory.m1_event_engine import extract_xauusd_m1_sma_crossover_events
from researchos.market_memory.m1_outcome_contract import M1OutcomeContract
from researchos.market_memory.outcome_engine import compute_forward_outcomes


def _event(direction: str = "bearish") -> MarketEvent:
    ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
    context = EventContext(
        event_id="e1", asset="XAUUSD", timeframe="M1", timestamp=ts, event_price=100.0
    )
    return MarketEvent(
        event_id="e1", asset="XAUUSD", timeframe="M1", event_type="sma_crossover",
        direction=direction, timestamp=ts, event_price=100.0, context=context,
    )


def test_contract_is_explicit_and_immutable():
    contract = M1OutcomeContract()
    assert contract.horizon_days == 1
    assert contract.label_name == "hit_threshold_1d"
    try:
        contract.horizon_days = 2
    except Exception:
        pass
    else:
        raise AssertionError("M1OutcomeContract must be immutable")


def test_bearish_label_and_full_window_excursions_are_direction_aware():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    timestamps = [start + timedelta(days=d) for d in range(3)]
    frame = pl.DataFrame({
        "timestamp": timestamps,
        "open": [100.0, 100.0, 100.0],
        "high": [101.0, 103.0, 101.0],
        "low": [99.0, 97.0, 95.0],
        "close": [100.0, 98.0, 96.0],
    })
    result = compute_forward_outcomes([_event()], frame, horizons=[1, 2], threshold=0.01)[0]
    assert result.outcome is not None
    assert result.outcome.hit_threshold_1d is True
    assert result.outcome.return_1d == -0.02
    assert result.outcome.mfe_1d == 0.03
    assert result.outcome.mae_1d == -0.03


def test_m1_event_extraction_is_deterministic():
    timestamps = [datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i) for i in range(8)]
    closes = [100.0, 99.0, 98.0, 97.0, 98.0, 99.0, 101.0, 103.0]
    frame = pl.DataFrame({
        "timestamp": timestamps,
        "open": closes,
        "high": [x + 0.2 for x in closes],
        "low": [x - 0.2 for x in closes],
        "close": closes,
        "tick_volume": [100] * len(closes),
    })
    first = extract_xauusd_m1_sma_crossover_events(frame, fast_period=2, slow_period=3)
    second = extract_xauusd_m1_sma_crossover_events(frame, fast_period=2, slow_period=3)
    assert first == second
    assert all(event.timeframe == "M1" for event in first)
    assert all(event.dataset_source == "xauusd_m1_mt5" for event in first)


def test_forward_outcome_rejects_integer_threshold_that_overflows_float():
    with pytest.raises(ValueError, match="threshold must be finite"):
        compute_forward_outcomes([], pl.DataFrame(), threshold=10**1000)
