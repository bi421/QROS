import math

import pytest

from researchos.orchestration.fast_three_state import FastThreeState


def test_returns_only_three_integer_states_and_warmup_fails_closed_to_range():
    engine = FastThreeState(lookback=8, min_move_bps=0)
    outputs = [engine.update(2000 + i) for i in range(8)]
    assert outputs[:7] == [0] * 7
    assert outputs[-1] == 1
    assert all(isinstance(value, int) and not isinstance(value, bool) and value in (-1, 0, 1) for value in outputs)


def test_monotonic_decline_is_down():
    engine = FastThreeState(lookback=8, min_move_bps=0)
    result = 0
    for i in range(8):
        result = engine.update(2000 - i)
    assert result == -1


def test_choppy_path_with_small_net_move_is_range():
    engine = FastThreeState(lookback=8, efficiency_threshold=0.35, min_move_bps=0)
    closes = [2000, 2002, 2000, 2002, 2000, 2002, 2000, 2001]
    result = 0
    for close in closes:
        result = engine.update(close)
    assert result == 0


def test_minimum_move_prevents_tiny_drift_being_called_trend():
    engine = FastThreeState(lookback=8, min_move_bps=5.0)
    result = 0
    for i in range(8):
        result = engine.update(2000.0 + i * 0.001)
    assert result == 0


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), -float("inf")])
def test_rejects_invalid_close(value):
    with pytest.raises(ValueError, match="finite and positive"):
        FastThreeState().update(value)


def test_rolling_memory_is_bounded_after_many_updates():
    engine = FastThreeState(lookback=16)
    for i in range(1000):
        engine.update(2000.0 + math.sin(i / 3.0))
    assert len(engine._closes) == 16
    assert len(engine._abs_returns) == 15
