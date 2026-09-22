"""
ResearchOS Macro Intelligence Layer - Rolling Statistics
Version: stat/roll/v1
Status: FROZEN

MIL-STAT-001: Same input must always produce identical output.
MIL-STAT-002: Statistical functions are pure.
MIL-STAT-004: All outputs preserve provenance.
"""

from __future__ import annotations

from researchos.macro.statistics.descriptive import mean, std, variance


def rolling_mean(
    values: list[float],
    window: int,
    min_periods: int | None = None,
) -> list[float | None]:
    """
    Calculate rolling mean.

    Args:
        values: List of numeric values
        window: Rolling window size
        min_periods: Minimum number of observations required

    Returns:
        List of rolling means (None if insufficient data)
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


def rolling_std(
    values: list[float],
    window: int,
    min_periods: int | None = None,
) -> list[float | None]:
    """
    Calculate rolling standard deviation.

    Args:
        values: List of numeric values
        window: Rolling window size
        min_periods: Minimum number of observations required

    Returns:
        List of rolling stds (None if insufficient data)
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
                result.append(std(window_values))
            else:
                result.append(None)

    return result


def rolling_variance(
    values: list[float],
    window: int,
    min_periods: int | None = None,
) -> list[float | None]:
    """
    Calculate rolling variance.

    Args:
        values: List of numeric values
        window: Rolling window size
        min_periods: Minimum number of observations required

    Returns:
        List of rolling variances (None if insufficient data)
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
                result.append(variance(window_values))
            else:
                result.append(None)

    return result


def rolling_zscore(
    values: list[float],
    window: int,
    min_periods: int | None = None,
) -> list[float | None]:
    """
    Calculate rolling z-score.

    Args:
        values: List of numeric values
        window: Rolling window size
        min_periods: Minimum number of observations required

    Returns:
        List of rolling z-scores (None if insufficient data)
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
                m = mean(window_values)
                s = std(window_values)
                if s == 0:
                    result.append(0.0)
                else:
                    result.append((values[i] - m) / s)
            else:
                result.append(None)

    return result


def rolling_percentile(
    values: list[float],
    window: int,
    percentile: float,
    min_periods: int | None = None,
) -> list[float | None]:
    """
    Calculate rolling percentile.

    Args:
        values: List of numeric values
        window: Rolling window size
        percentile: Percentile to calculate (0-100)
        min_periods: Minimum number of observations required

    Returns:
        List of rolling percentiles (None if insufficient data)
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
                result.append(percentile(window_values, percentile))
            else:
                result.append(None)

    return result


def rolling_statistics(
    values: list[float],
    window: int,
    min_periods: int | None = None,
) -> list[dict[str, float | None]]:
    """
    Calculate complete rolling statistics.

    Args:
        values: List of numeric values
        window: Rolling window size
        min_periods: Minimum number of observations required

    Returns:
        List of dictionaries containing rolling statistics
    """
    if min_periods is None:
        min_periods = window

    result: list[dict[str, float | None]] = []
    for i in range(len(values)):
        if i < window - 1:
            result.append(
                {
                    "mean": None,
                    "std": None,
                    "variance": None,
                    "min": None,
                    "max": None,
                    "count": 0,
                }
            )
        else:
            window_values = values[i - window + 1 : i + 1]
            if len(window_values) >= min_periods:
                result.append(
                    {
                        "mean": mean(window_values),
                        "std": std(window_values),
                        "variance": variance(window_values),
                        "min": min(window_values),
                        "max": max(window_values),
                        "count": len(window_values),
                    }
                )
            else:
                result.append(
                    {
                        "mean": None,
                        "std": None,
                        "variance": None,
                        "min": None,
                        "max": None,
                        "count": 0,
                    }
                )

    return result


def expanding_mean(values: list[float]) -> list[float]:
    """
    Calculate expanding mean.

    Args:
        values: List of numeric values

    Returns:
        List of expanding means
    """
    result: list[float] = []
    for i in range(len(values)):
        result.append(mean(values[: i + 1]))
    return result


def expanding_std(values: list[float]) -> list[float]:
    """
    Calculate expanding standard deviation.

    Args:
        values: List of numeric values

    Returns:
        List of expanding stds
    """
    result: list[float] = []
    for i in range(len(values)):
        result.append(std(values[: i + 1]))
    return result
