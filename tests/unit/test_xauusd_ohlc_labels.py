"""Tests for the additive OHLC-aware XAUUSD triple-barrier labeler."""
from datetime import datetime, timedelta, timezone

import pytest

from researchos.orchestration.xauusd_labels import (
    OHLCBar,
    label_ohlc_triple_barrier,
)
from researchos.orchestration.xauusd_research import OutcomeLabel, OutcomeSpec


BASE = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)


def bars(rows):
    return [
        OHLCBar(BASE + timedelta(minutes=15 * i), *row)
        for i, row in enumerate(rows)
    ]


def inputs(rows, direction=1, atr_value=1.0, spec=None):
    candles = bars(rows)
    directions = [direction] * len(candles)
    atr = [atr_value] * len(candles)
    return label_ohlc_triple_barrier(candles, directions, atr, spec)


def test_long_take_profit_uses_next_bar_open_and_ohlc_high():
    result = inputs([
        (100, 101, 99, 100),
        (100, 100.5, 99.5, 100),
        (100, 102, 99.5, 101),
        (101, 101.5, 100.5, 101),
    ], spec=OutcomeSpec(take_profit_atr=1.5, stop_loss_atr=1.0, max_holding_bars=2))
    assert result[0] is not None
    assert result[0].outcome is OutcomeLabel.TAKE_PROFIT
    assert result[0].entry_price == 100
    assert result[0].exit_price == 101.5
    assert result[0].bars_held == 2


def test_short_stop_loss_uses_high():
    result = inputs([
        (100, 101, 99, 100),
        (100, 100.5, 99.5, 100),
        (100, 101.5, 99.0, 100),
        (100, 100.5, 99.5, 100),
    ], direction=-1,
       spec=OutcomeSpec(take_profit_atr=1.5, stop_loss_atr=1.0, max_holding_bars=2))
    assert result[0] is not None
    assert result[0].outcome is OutcomeLabel.STOP_LOSS
    assert result[0].exit_price == 101


def test_both_barriers_touched_excludes_by_default():
    result = inputs([
        (100, 101, 99, 100),
        (100, 100.5, 99.5, 100),
        (100, 102, 98, 100),
        (100, 100.5, 99.5, 100),
    ], spec=OutcomeSpec(take_profit_atr=1.5, stop_loss_atr=1.0, max_holding_bars=2))
    assert result[0] is None


def test_both_barriers_touched_can_use_conservative_stop_first():
    result = inputs([
        (100, 101, 99, 100),
        (100, 100.5, 99.5, 100),
        (100, 102, 98, 100),
        (100, 100.5, 99.5, 100),
    ], spec=OutcomeSpec(
        take_profit_atr=1.5,
        stop_loss_atr=1.0,
        max_holding_bars=2,
        ambiguous_touch_policy="CONSERVATIVE_SL_FIRST",
    ))
    assert result[0] is not None
    assert result[0].outcome is OutcomeLabel.STOP_LOSS
    assert result[0].exit_price == 99


def test_timeout_requires_full_forward_window():
    result = inputs([
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
    ], spec=OutcomeSpec(take_profit_atr=5, stop_loss_atr=5, max_holding_bars=2))
    assert result[0] is not None
    assert result[0].outcome is OutcomeLabel.TIMEOUT
    assert result[0].bars_held == 2
    assert result[-2] is None
    assert result[-1] is None


def test_missing_atr_or_no_signal_is_not_labeled():
    candles = bars([(100, 101, 99, 100)] * 4)
    result = label_ohlc_triple_barrier(candles, [1, None, 1, 1], [None, 1, 1, 1],
                                       OutcomeSpec(max_holding_bars=2))
    assert result[0] is None
    assert result[1] is None


@pytest.mark.parametrize("rows", [
    [(100, 99, 98, 100)],
    [(100, 101, 102, 100)],
    [(100, float("nan"), 99, 100)],
])
def test_invalid_ohlc_fails_closed(rows):
    with pytest.raises(ValueError):
        bars(rows)


def test_non_chronological_bars_are_rejected():
    candles = bars([(100, 101, 99, 100)] * 3)
    candles[1] = OHLCBar(BASE, 100, 101, 99, 100)
    with pytest.raises(ValueError, match="strictly increasing"):
        label_ohlc_triple_barrier(candles, [1, 1, 1], [1, 1, 1])


def test_input_lengths_and_directions_are_validated():
    candles = bars([(100, 101, 99, 100)] * 3)
    with pytest.raises(ValueError, match="equal lengths"):
        label_ohlc_triple_barrier(candles, [1], [1, 1, 1])
    with pytest.raises(ValueError, match="directions"):
        label_ohlc_triple_barrier(candles, [0, 1, 1], [1, 1, 1])
