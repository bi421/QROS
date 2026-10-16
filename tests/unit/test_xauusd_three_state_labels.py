from datetime import datetime, timedelta, timezone

import pytest

from researchos.orchestration.xauusd_labels import OHLCBar
from researchos.orchestration.xauusd_three_state_labels import label_three_state_triple_barrier

BASE = datetime(2026, 10, 1, tzinfo=timezone.utc)


def make_bars(rows):
    return [OHLCBar(BASE + timedelta(minutes=i), *row) for i, row in enumerate(rows)]


def test_upper_barrier_is_up_and_uses_future_bars_only():
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 100.5, 99.5, 100),
        (100, 102, 99.5, 101),
        (101, 101.5, 100.5, 101),
    ])
    labels = label_three_state_triple_barrier(bars, [1.0] * 4, upper_atr=1.5, lower_atr=1.5, max_holding_bars=2)
    assert labels[0] == "UP"


def test_lower_barrier_is_down():
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 100.5, 99.5, 100),
        (100, 100.5, 98, 99),
        (99, 99.5, 98.5, 99),
    ])
    labels = label_three_state_triple_barrier(bars, [1.0] * 4, max_holding_bars=2)
    assert labels[0] == "DOWN"


def test_vertical_barrier_becomes_range():
    bars = make_bars([(100, 100.5, 99.5, 100)] * 4)
    labels = label_three_state_triple_barrier(bars, [1.0] * 4, max_holding_bars=2)
    assert labels[0] == "RANGE"


def test_same_bar_double_touch_is_excluded_as_ambiguous():
    bars = make_bars([
        (100, 100.5, 99.5, 100),
        (100, 102, 98, 100),
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
    ])
    labels = label_three_state_triple_barrier(bars, [1.0] * 4, max_holding_bars=2)
    assert labels[0] is None


def test_incomplete_horizon_and_missing_atr_are_not_labeled():
    bars = make_bars([(100, 100.5, 99.5, 100)] * 3)
    labels = label_three_state_triple_barrier(bars, [1.0, None, 1.0], max_holding_bars=2)
    assert labels[0] == "RANGE"
    assert labels[1] is None
    assert labels[2] is None


def test_rejects_invalid_parameters_and_lengths():
    bars = make_bars([(100, 100.5, 99.5, 100)] * 3)
    with pytest.raises(ValueError, match="equal lengths"):
        label_three_state_triple_barrier(bars, [1.0])
    with pytest.raises(ValueError, match="upper_atr"):
        label_three_state_triple_barrier(bars, [1.0] * 3, upper_atr=0)
    with pytest.raises(ValueError, match="positive integer"):
        label_three_state_triple_barrier(bars, [1.0] * 3, max_holding_bars=0)
