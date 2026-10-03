"""
Pure Python technical indicators. No external dependencies (numpy/pandas).
"""

from collections.abc import Sequence


def calculate_rsi(prices: Sequence[float], period: int = 14) -> list[float]:
    if len(prices) < period + 1:
        return []
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi_values: list[float] = []
    if avg_loss == 0:
        rsi_values.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsi_values.append(100.0 - (100.0 / (1.0 + rs)))
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100.0 - (100.0 / (1.0 + rs)))
    return rsi_values


def _calculate_ema(prices: Sequence[float], period: int) -> list[float]:
    multiplier = 2.0 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for price in prices[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return ema


def calculate_macd(
    prices: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[float], list[float], list[float]]:
    if len(prices) < slow + signal:
        return [], [], []
    ema_fast = _calculate_ema(prices, fast)
    ema_slow = _calculate_ema(prices, slow)
    offset = slow - fast
    macd_line = [ema_fast[i + offset] - ema_slow[i] for i in range(len(ema_slow))]
    signal_line = _calculate_ema(macd_line, signal)
    offset_sig = len(macd_line) - len(signal_line)
    histogram = [macd_line[i + offset_sig] - signal_line[i] for i in range(len(signal_line))]
    start_idx = offset + offset_sig
    return macd_line[start_idx:], signal_line, histogram


def calculate_bollinger_bands(
    prices: Sequence[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[list[float], list[float], list[float]]:
    if len(prices) < period:
        return [], [], []
    upper: list[float] = []
    middle: list[float] = []
    lower: list[float] = []
    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1 : i + 1]
        sma = sum(window) / period
        variance = sum((x - sma) ** 2 for x in window) / period
        std = variance**0.5
        middle.append(sma)
        upper.append(sma + std_dev * std)
        lower.append(sma - std_dev * std)
    return upper, middle, lower
