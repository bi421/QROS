"""RSI output-length, warmup alignment, and degenerate-market regression tests."""

from researchos.market_memory.event_extractor import _compute_rsi


def test_rsi_has_one_value_per_close_for_minimum_valid_input() -> None:
    closes = [float(value) for value in range(10, 25)]
    result = _compute_rsi(closes, period=14)
    assert len(result) == len(closes)
    assert result[:14] == [50.0] * 14
    assert result[14] == 100.0


def test_rsi_has_one_value_per_close_for_longer_series() -> None:
    closes = [100.0, 101.0, 99.0, 102.0, 101.0, 103.0, 100.0, 104.0]
    result = _compute_rsi(closes, period=3)
    assert len(result) == len(closes)


def test_rsi_flat_prices_are_neutral() -> None:
    result = _compute_rsi([100.0] * 20, period=5)
    assert len(result) == 20
    assert result[5:] == [50.0] * 15


def test_rsi_strictly_falling_prices_reach_zero() -> None:
    result = _compute_rsi([float(100 - i) for i in range(20)], period=5)
    assert len(result) == 20
    assert result[5] == 0.0
