from datetime import datetime
import pytest
from researchos.orchestration.triple_barrier import triple_barrier_label
from researchos.orchestration.kinetic_regime_filter import (
    classify_session,
    volatility_gate,
    speed_curvature_interaction,
)


def test_triple_barrier_up_down_ambiguous_and_timeout():
    o = [100, 100, 101, 100, 100, 100]
    h = [100.5, 102, 103, 100.5, 100.5, 100.5]
    lo = [99.5, 99.5, 98, 99.5, 99.5, 99.5]
    c = [100, 101, 100, 100, 100, 100]
    atr = [1.0] * 6
    assert triple_barrier_label(o, h, lo, c, atr, 0, vertical_barrier=2)["label"] == "UP_FIRST"
    assert triple_barrier_label(o, h, lo, c, atr, 1, vertical_barrier=2)["label"] == "AMBIGUOUS"
    assert triple_barrier_label(o, h, lo, c, atr, 3, vertical_barrier=2)["label"] == "TIMEOUT"


def test_triple_barrier_does_not_label_incomplete_future_as_timeout():
    result = triple_barrier_label(
        [100, 100], [101, 101], [99, 99], [100, 100], [1.0, 1.0], 0, vertical_barrier=2
    )
    assert result["label"] == "UNAVAILABLE"


def test_triple_barrier_rejects_bad_ohlc_and_missing_atr():
    with pytest.raises(ValueError):
        triple_barrier_label([100, 100], [99, 101], [98, 99], [100, 100], [1, 1], 0)
    result = triple_barrier_label([100, 100], [101, 101], [99, 99], [100, 100], [None, 1], 0)
    assert result["label"] == "UNAVAILABLE"


def test_volatility_gate_uses_prior_only_and_warms_up_fail_closed():
    assert volatility_gate([1, 2, 3], 100, min_history=5)["status"] == "WARMUP"
    result = volatility_gate(list(range(1, 101)), 100, min_history=50, percentile_floor=0.8)
    assert result["eligible"] is True
    assert result["threshold"] <= 100
    assert (
        volatility_gate(list(range(1, 101)), 1, min_history=50, percentile_floor=0.8)["eligible"]
        is False
    )


def test_session_and_interaction_features():
    assert classify_session(datetime(2025, 1, 1, 3)) == "ASIA"
    assert classify_session(datetime(2025, 1, 1, 9)) == "LONDON"
    assert classify_session(datetime(2025, 1, 1, 15)) == "NEW_YORK_OVERLAP"
    assert speed_curvature_interaction(2.0, -0.25) == pytest.approx(-0.5)
    assert speed_curvature_interaction(2.0, None) is None
