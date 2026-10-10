"""Regression tests for statistical evidence and production gates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from researchos.market_memory.conditioning import compute_conditional_statistics
from researchos.market_memory.event_schema import (
    ConditionSpec,
    EventContext,
    EventOutcome,
    MarketEvent,
)
from researchos.market_memory.production_gate import check_production_evidence_readiness
from researchos.market_memory.statistical_evidence import bonferroni_alpha, wilson_proportion_ci


def _event(
    i: int,
    outcome: float = 0.01,
    source: str = "real_mt5",
    direction: str = "bullish",
) -> MarketEvent:
    ts = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)
    context = EventContext(event_id=f"e{i}", asset="XAUUSD", timeframe="D1", timestamp=ts)
    return MarketEvent(
        event_id=f"e{i}", asset="XAUUSD", timeframe="D1", event_type="sma_crossover",
        direction=direction, timestamp=ts, event_price=2000.0, context=context,
        outcome=EventOutcome(event_id=f"e{i}", asset="XAUUSD", timeframe="D1", event_timestamp=ts, return_1d=outcome),
        dataset_source=source,
    )


def test_wilson_interval_is_bounded_and_deterministic():
    a = wilson_proportion_ci(7, 10)
    b = wilson_proportion_ci(7, 10)
    assert a == b
    assert 0.0 <= a.confidence_interval[0] <= a.probability <= a.confidence_interval[1] <= 1.0


def test_wilson_rejects_invalid_counts():
    with pytest.raises(ValueError):
        wilson_proportion_ci(11, 10)
    with pytest.raises(ValueError):
        wilson_proportion_ci(1, 0)


def test_bonferroni_alpha():
    assert bonferroni_alpha(0.05, 5) == pytest.approx(0.01)


def test_production_gate_accepts_real_provenance():
    result = check_production_evidence_readiness([_event(i) for i in range(100)], dataset_source="real_mt5", minimum_events=100)
    assert result.passed is True
    assert result.issues == ()


def test_production_gate_rejects_synthetic():
    result = check_production_evidence_readiness([_event(i, source="synthetic") for i in range(100)], dataset_source="synthetic")
    assert result.passed is False
    assert any("blocked evidence source" in issue for issue in result.issues)


def test_production_gate_rejects_missing_outcome():
    event = _event(0)
    broken = MarketEvent(
        event_id=event.event_id, asset=event.asset, timeframe=event.timeframe,
        event_type=event.event_type, direction=event.direction, timestamp=event.timestamp,
        event_price=event.event_price, context=event.context, outcome=None,
        dataset_source=event.dataset_source,
    )
    result = check_production_evidence_readiness([broken], dataset_source="real_mt5", minimum_events=1)
    assert result.passed is False
    assert any("missing outcome" in issue for issue in result.issues)



def test_conditional_probability_distinguishes_raw_and_directional_success() -> None:
    events = [
        _event(0, outcome=-1.0, direction="bearish"),
        _event(1, outcome=-2.0, direction="bearish"),
        _event(2, outcome=-3.0, direction="bearish"),
        _event(3, outcome=1.0, direction="bearish"),
    ]
    result = compute_conditional_statistics(
        events,
        ConditionSpec(name="bearish_all", conditions={}),
        bootstrap_num_resamples=20,
    )

    # Raw probability remains P(return > 0), for backward-compatible meaning.
    assert result.raw_probability == pytest.approx(0.25)
    # Directional probability measures the share moving with the bearish signal.
    assert result.directional_probability == pytest.approx(0.75)
    assert "not direction-adjusted signal success" in result.probability_definition
    serialized = result.to_dict()
    assert serialized["raw_probability"] == pytest.approx(0.25)
    assert serialized["directional_probability"] == pytest.approx(0.75)


def test_directional_probability_is_unavailable_for_unknown_direction() -> None:
    events = [_event(0, outcome=1.0, direction="sideways")]
    result = compute_conditional_statistics(
        events,
        ConditionSpec(name="unknown_direction", conditions={}),
        bootstrap_num_resamples=5,
    )

    assert result.raw_probability == pytest.approx(1.0)
    assert result.directional_probability is None
    assert "not bullish/bearish" in result.notes
