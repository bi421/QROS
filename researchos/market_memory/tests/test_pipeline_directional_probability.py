from datetime import datetime, timedelta, timezone

from researchos.market_memory.event_schema import ConditionSpec, EventContext, EventOutcome, MarketEvent
from researchos.market_memory.pipeline_v1 import _directional_success_counts


def _event(index: int, direction: str, outcome: float) -> MarketEvent:
    timestamp = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)
    context = EventContext(
        event_id=f"event-{index}",
        asset="XAUUSD",
        timeframe="D1",
        timestamp=timestamp,
    )
    return MarketEvent(
        event_id=f"event-{index}",
        asset="XAUUSD",
        timeframe="D1",
        event_type="sma_crossover",
        direction=direction,
        timestamp=timestamp,
        event_price=2000.0,
        context=context,
        outcome=EventOutcome(
            event_id=f"event-{index}",
            asset="XAUUSD",
            timeframe="D1",
            event_timestamp=timestamp,
            return_1d=outcome,
        ),
    )


def test_directional_success_counts_reverse_bearish_return_sign():
    events = [
        _event(0, "bearish", -0.01),
        _event(1, "bearish", -0.02),
        _event(2, "bearish", -0.03),
        _event(3, "bearish", 0.01),
    ]
    counts = _directional_success_counts(events, ConditionSpec(name="all", conditions={}))
    assert counts == (3, 4)


def test_directional_success_counts_fail_closed_on_unknown_direction():
    events = [
        _event(0, "bullish", 0.01),
        _event(1, "sideways", -0.01),
    ]
    counts = _directional_success_counts(events, ConditionSpec(name="all", conditions={}))
    assert counts is None


def test_directional_success_counts_ignore_non_finite_outcomes():
    events = [
        _event(0, "bullish", 0.01),
        _event(1, "bearish", float("nan")),
    ]
    counts = _directional_success_counts(events, ConditionSpec(name="all", conditions={}))
    assert counts == (1, 1)
