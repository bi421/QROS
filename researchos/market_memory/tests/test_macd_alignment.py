"""Regression tests for MACD signal alignment and zero-valued observations."""

from __future__ import annotations

import math

from researchos.market_memory.event_extractor import _compute_macd


def _reference_ema(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    current = sum(values[:period]) / period
    result[period - 1] = current
    alpha = 2.0 / (period + 1)
    for index in range(period, len(values)):
        current = alpha * values[index] + (1.0 - alpha) * current
        result[index] = current
    return result


def test_macd_signal_matches_ema_of_full_macd_series() -> None:
    closes = [
        100.0 + math.sin(index / 3.0) * 4.0 + index * 0.07
        for index in range(120)
    ]
    fast, slow, signal = 5, 11, 4
    macd_line, signal_line, histogram = _compute_macd(
        closes, fast=fast, slow=slow, signal=signal
    )

    fast_ema = _reference_ema(closes, fast)
    slow_ema = _reference_ema(closes, slow)
    expected_macd = [
        (fast_ema[i] - slow_ema[i])
        if fast_ema[i] is not None and slow_ema[i] is not None
        else 0.0
        for i in range(len(closes))
    ]
    valid_start = slow - 1
    expected_signal_values = _reference_ema(expected_macd[valid_start:], signal)
    expected_signal = [0.0] * len(closes)
    for offset, value in enumerate(expected_signal_values):
        if value is not None:
            expected_signal[valid_start + offset] = value

    assert macd_line == expected_macd
    assert signal_line == expected_signal
    assert histogram == [
        expected_macd[i] - expected_signal[i] for i in range(len(closes))
    ]


def test_macd_signal_preserves_zero_values_after_warmup() -> None:
    # Flat prices produce real zero MACD values; these observations must remain
    # in the signal EMA input rather than being filtered out by value.
    closes = [100.0] * 80
    macd_line, signal_line, histogram = _compute_macd(
        closes, fast=5, slow=11, signal=4
    )

    assert all(value == 0.0 for value in macd_line)
    assert all(value == 0.0 for value in signal_line)
    assert all(value == 0.0 for value in histogram)
