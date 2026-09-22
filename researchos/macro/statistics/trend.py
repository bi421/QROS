"""
ResearchOS Macro Intelligence Layer - Trend Analysis
Version: stat/trend/v1
Status: FROZEN

MIL-STAT-001: Same input must always produce identical output.
MIL-STAT-002: Statistical functions are pure.
"""

from __future__ import annotations

from typing import Any

from researchos.macro.statistics.descriptive import mean
from researchos.macro.statistics.regression import linear_regression


def moving_average(
    values: list[float],
    window: int,
    min_periods: int | None = None,
) -> list[float | None]:
    """
    Calculate simple moving average.

    Args:
        values: List of numeric values
        window: Moving average window
        min_periods: Minimum number of observations

    Returns:
        List of moving averages
    """
    if min_periods is None:
        min_periods = window

    result: list[float | None] = []
    for i in range(len(values)):
        if i < window - 1:
            result.append(None)
        else:
            window_values = values[i - window + 1 : i + 1]
            if len(window_values) >= min_periods:
                result.append(mean(window_values))
            else:
                result.append(None)

    return result


def exponential_moving_average(
    values: list[float],
    span: int,
    adjust: bool = True,
) -> list[float]:
    """
    Calculate exponential moving average.

    Args:
        values: List of numeric values
        span: EMA span (similar to window)
        adjust: Whether to adjust for biases

    Returns:
        List of EMA values
    """
    if not values:
        return []

    alpha = 2.0 / (span + 1.0)
    result = [values[0]]

    for i in range(1, len(values)):
        if adjust:
            # Adjusted EMA
            result.append(alpha * values[i] + (1 - alpha) * result[-1])
        else:
            # Unadjusted EMA
            result.append(alpha * values[i] + (1 - alpha) * result[-1])

    return result


def trend_strength(
    values: list[float],
    window: int = 20,
) -> float:
    """
    Calculate trend strength using Hurst exponent approximation.

    Args:
        values: List of numeric values
        window: Window for calculation

    Returns:
        Trend strength (0 to 1)
    """
    if len(values) < window:
        return 0.0

    # Use recent values
    recent = values[-window:]

    # Calculate returns
    returns = [recent[i] - recent[i - 1] for i in range(1, len(recent))]

    if not returns:
        return 0.0

    # Calculate autocorrelation of returns
    mean_ret = mean(returns)
    var_ret = sum((r - mean_ret) ** 2 for r in returns) / len(returns)

    if var_ret == 0:
        return 0.0

    # Simple trend strength: ratio of first-order autocorrelation
    if len(returns) < 2:
        return 0.0

    cov = sum((returns[i] - mean_ret) * (returns[i - 1] - mean_ret) for i in range(1, len(returns))) / (len(returns) - 1)

    autocorr = cov / var_ret

    # Convert to trend strength (0 to 1)
    return abs(autocorr)


def momentum(
    values: list[float],
    period: int = 1,
) -> list[float | None]:
    """
    Calculate momentum (rate of change).

    Args:
        values: List of numeric values
        period: Momentum period

    Returns:
        List of momentum values
    """
    result = []
    for i in range(len(values)):
        if i < period:
            result.append(None)
        else:
            result.append(values[i] - values[i - period])

    return result


def rate_of_change(
    values: list[float],
    period: int = 1,
) -> list[float | None]:
    """
    Calculate rate of change (percentage).

    Args:
        values: List of numeric values
        period: ROC period

    Returns:
        List of ROC values
    """
    result = []
    for i in range(len(values)):
        if i < period or values[i - period] == 0:
            result.append(None)
        else:
            result.append(((values[i] - values[i - period]) / values[i - period]) * 100)

    return result


def trend_analysis(
    values: list[float],
    window: int = 20,
) -> dict[str, Any]:
    """
    Complete trend analysis.

    Args:
        values: List of numeric values
        window: Window for calculations

    Returns:
        Dictionary with trend metrics
    """
    if len(values) < window:
        return {
            "trend_direction": "insufficient_data",
            "trend_strength": 0.0,
            "momentum": None,
            "slope": None,
        }

    # Calculate slope using linear regression
    x = [float(i) for i in range(len(values))]
    reg = linear_regression(x, values)

    # Calculate trend strength
    strength = trend_strength(values, window)

    # Calculate momentum
    mom = momentum(values, 1)[-1] if values else None

    # Determine trend direction
    if reg.slope > 0:
        direction = "upward"
    elif reg.slope < 0:
        direction = "downward"
    else:
        direction = "flat"

    return {
        "trend_direction": direction,
        "trend_strength": strength,
        "momentum": mom,
        "slope": reg.slope,
        "intercept": reg.intercept,
        "r_squared": reg.r_squared,
    }
