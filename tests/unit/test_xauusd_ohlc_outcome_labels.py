"""Tests for the additive OHLC triple-barrier labeler."""

import pytest

from researchos.orchestration.xauusd_research import OutcomeLabel, OutcomeSpec
from researchos.quant_engine.machine_learning.ohlc_triple_barrier import (
    OHLCBar,
    label_ohlc_outcomes,
)


def bars(*items):
    return tuple(OHLCBar(*item) for item in items)


def spec(**overrides):
    values = {
        "atr_period": 1,
        "take_profit_atr": 2.0,
        "stop_loss_atr": 1.0,
        "max_holding_bars": 2,
    }
    values.update(overrides)
    return OutcomeSpec(**values)


def test_long_take_profit_is_first_touch_from_next_bar_open():
    data = bars(
        (100, 101, 99, 100),
        (100, 103, 99.5, 102),
        (102, 103, 101, 102),
    )
    result = label_ohlc_outcomes(data, [1, 1, 1], [1, 1, 1], spec())
    assert result[0].entry_index == 1
    assert result[0].label is OutcomeLabel.TAKE_PROFIT
    assert result[0].reason_code == "TAKE_PROFIT_FIRST_TOUCH"


def test_short_stop_loss_is_first_touch():
    data = bars(
        (100, 101, 99, 100),
        (100, 101.5, 98, 99),
        (99, 100, 98, 99),
    )
    result = label_ohlc_outcomes(data, [-1, -1, -1], [1, 1, 1], spec())
    assert result[0].label is OutcomeLabel.STOP_LOSS


def test_same_bar_ambiguous_touch_is_excluded_by_default():
    data = bars(
        (100, 101, 99, 100),
        (100, 103, 98.5, 101),
        (101, 102, 100, 101),
    )
    result = label_ohlc_outcomes(data, [1, 1, 1], [1, 1, 1], spec())
    assert result[0].label is None
    assert result[0].reason_code == "AMBIGUOUS_SAME_BAR_TOUCH"


def test_same_bar_ambiguous_touch_can_be_conservative_stop_first():
    data = bars(
        (100, 101, 99, 100),
        (100, 103, 98.5, 101),
        (101, 102, 100, 101),
    )
    result = label_ohlc_outcomes(
        data, [1, 1, 1], [1, 1, 1],
        spec(ambiguous_touch_policy="CONSERVATIVE_SL_FIRST"),
    )
    assert result[0].label is OutcomeLabel.STOP_LOSS


def test_timeout_requires_full_horizon():
    data = bars(
        (100, 101, 99, 100),
        (100, 101, 99.5, 100),
        (100, 101, 99.5, 100),
    )
    result = label_ohlc_outcomes(data, [1, 1, 1], [1, 1, 1], spec())
    assert result[0].label is OutcomeLabel.TIMEOUT
    assert result[0].reason_code == "HORIZON_TIMEOUT"
    assert result[1].label is None
    assert result[1].reason_code == "HORIZON_INCOMPLETE"


def test_entry_is_next_bar_open_not_decision_bar_close():
    data = bars(
        (100, 110, 99, 109),
        (120, 121, 119, 120),
        (120, 121, 119, 120),
    )
    result = label_ohlc_outcomes(data, [1, 1, 1], [1, 1, 1], spec())
    assert result[0].entry_index == 1
    assert result[0].label is OutcomeLabel.TIMEOUT


@pytest.mark.parametrize("atr", [None, 0, -1, float("nan"), float("inf")])
def test_missing_or_invalid_atr_is_unlabelable(atr):
    data = bars(
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 101, 99, 100),
    )
    result = label_ohlc_outcomes(data, [1, 1, 1], [atr, 1, 1], spec())
    assert result[0].label is None
    assert result[0].reason_code in {"ATR_MISSING", "ATR_INVALID"}


def test_rejects_ohlc_bounds_and_mismatched_lengths():
    with pytest.raises(ValueError, match="inconsistent OHLC"):
        label_ohlc_outcomes(
            bars((100, 99, 98, 100)), [1], [1], spec()
        )
    data = bars((100, 101, 99, 100))
    with pytest.raises(ValueError, match="equal lengths"):
        label_ohlc_outcomes(data, [1, 1], [1], spec())


def test_neutral_direction_is_not_fabricated_as_timeout():
    data = bars(
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 101, 99, 100),
    )
    result = label_ohlc_outcomes(data, [0, 1, 1], [1, 1, 1], spec())
    assert result[0].label is None
    assert result[0].reason_code == "NEUTRAL_DIRECTION"
