"""
Statistical functions for the Quant Computation Engine.

All calculations are:
    - Deterministic: Same inputs → same outputs
    - Versioned: CalculationVersion controls formula selection
    - Safe: Handles empty datasets, insufficient samples, zero variance, invalid inputs
    - Pure Python: No external dependencies (no numpy, no scipy)

Based on Article XVII: Object Model — Quant Engine Layer.
"""

from __future__ import annotations

import math
from typing import Any

from researchos.quant_engine.models import CalculationVersion


def _validate_returns(returns: list[float], min_samples: int = 2) -> None:
    """Validate that returns data is sufficient for calculation."""
    if not returns:
        raise ValueError("Cannot compute statistics on empty dataset")
    if len(returns) < min_samples:
        raise ValueError(f"Insufficient samples: need at least {min_samples}, got {len(returns)}")


def mean(returns: list[float]) -> float:
    """Compute the arithmetic mean of a list of returns."""
    _validate_returns(returns, min_samples=1)
    return math.fsum(value / len(returns) for value in returns)


def variance(returns: list[float], ddof: int = 1) -> float:
    """
    Compute the variance of returns.

    Uses sample variance (ddof=1) by default for unbiased estimation.
    Uses population variance (ddof=0) when the full population is known.

    Args:
        returns: List of periodic returns.
        ddof: Delta degrees of freedom (1 for sample, 0 for population).

    Returns:
        Variance value.

    Raises:
        ValueError: If returns has fewer than 2 elements (for ddof=1).
    """
    if ddof == 0:
        _validate_returns(returns, min_samples=1)
    else:
        _validate_returns(returns, min_samples=2)

    avg = mean(returns)
    squared_diffs = sum((r - avg) ** 2 for r in returns)
    return squared_diffs / (len(returns) - ddof)


def standard_deviation(returns: list[float], ddof: int = 1) -> float:
    """
    Compute the standard deviation of returns.

    Args:
        returns: List of periodic returns.
        ddof: Delta degrees of freedom.

    Returns:
        Standard deviation value.

    Raises:
        ValueError: If insufficient samples.
    """
    return math.sqrt(variance(returns, ddof=ddof))


def rolling_volatility(
    returns: list[float],
    window: int = 21,
    ddof: int = 1,
) -> list[float]:
    """
    Compute rolling volatility over a sliding window.

    Args:
        returns: List of periodic returns.
        window: Size of the rolling window in periods.
        ddof: Delta degrees of freedom.

    Returns:
        List of rolling volatility values (length = len(returns) - window + 1).

    Raises:
        ValueError: If returns is shorter than window.
    """
    _validate_returns(returns, min_samples=window)
    if len(returns) < window:
        raise ValueError(f"Window size {window} exceeds data length {len(returns)}")

    vols: list[float] = []
    for i in range(len(returns) - window + 1):
        window_returns = returns[i : i + window]
        vols.append(standard_deviation(window_returns, ddof=ddof))

    return vols


def volatility_change(
    returns: list[float],
    window: int = 21,
    ddof: int = 1,
) -> float:
    """
    Compute the change in volatility between the first and second half of the period.

    Volatility_Change = (Recent_Vol - Early_Vol) / Early_Vol

    Positive values indicate increasing volatility. Negative values indicate decreasing.

    Args:
        returns: List of periodic returns.
        window: Window size for each half.
        ddof: Delta degrees of freedom.

    Returns:
        Volatility change as a decimal.

    Raises:
        ValueError: If returns has fewer than 2*window elements.
    """
    min_required = window * 2
    if len(returns) < min_required:
        raise ValueError(f"Need at least {min_required} returns for volatility change, got {len(returns)}")

    early = returns[:window]
    recent = returns[-window:]

    early_vol = standard_deviation(early, ddof=ddof)
    recent_vol = standard_deviation(recent, ddof=ddof)

    if early_vol == 0.0:
        if recent_vol > 0.0:
            return float("inf")
        return 0.0

    return (recent_vol - early_vol) / early_vol


def skewness(returns: list[float]) -> float:
    """
    Compute the skewness of the return distribution.

    Measures asymmetry: positive skew = right tail, negative skew = left tail.

    Args:
        returns: List of periodic returns.

    Returns:
        Skewness value (0.0 for normal distribution).

    Raises:
        ValueError: If fewer than 3 samples.
    """
    _validate_returns(returns, min_samples=3)
    avg = mean(returns)
    std = standard_deviation(returns, ddof=0)

    if std == 0.0:
        return 0.0

    n = len(returns)
    cubed_deviations = sum(((r - avg) / std) ** 3 for r in returns)
    return (n / ((n - 1) * (n - 2))) * cubed_deviations


def kurtosis(returns: list[float], excess: bool = True) -> float:
    """
    Compute the kurtosis of the return distribution.

    Measures tailedness: higher values = fatter tails.
    By default returns excess kurtosis (normal distribution = 0.0).

    Args:
        returns: List of periodic returns.
        excess: If True, subtract 3 for excess kurtosis.

    Returns:
        Kurtosis value (0.0 for normal distribution with excess=True).

    Raises:
        ValueError: If fewer than 4 samples.
    """
    _validate_returns(returns, min_samples=4)
    avg = mean(returns)
    std = standard_deviation(returns, ddof=0)

    if std == 0.0:
        return 0.0

    n = len(returns)
    fourth_power = sum(((r - avg) / std) ** 4 for r in returns)

    numerator = n * (n + 1) * fourth_power
    denominator = (n - 1) * (n - 2) * (n - 3)
    result = numerator / denominator if denominator != 0 else 0.0

    if excess:
        # Excess kurtosis: subtract 3 * (n-1)^2 / ((n-2)*(n-3))
        correction = (3 * (n - 1) ** 2) / ((n - 2) * (n - 3)) if (n > 3) else 3.0
        result -= correction

    return result


def z_score(value: float, population_mean: float, population_std: float) -> float:
    """
    Compute the z-score of a value relative to a population.

    Z = (value - mean) / std

    Args:
        value: The value to standardize.
        population_mean: Mean of the population.
        population_std: Standard deviation of the population.

    Returns:
        Z-score value.

    Raises:
        ValueError: If population_std is zero or negative.
    """
    if population_std <= 0:
        raise ValueError(f"Cannot compute z-score with non-positive std: {population_std}")
    return (value - population_mean) / population_std


def calculate_returns_from_prices(
    prices: list[float],
    return_type: str = "percentage",
    calculation_version: CalculationVersion = CalculationVersion.CALCULATION_V1,
) -> list[float]:
    """
    Calculate returns from an ordered price series.

    Supported return types:
        - "absolute": r_i = p_i - p_{i-1}
        - "percentage": r_i = (p_i - p_{i-1}) / p_{i-1}
        - "log": r_i = ln(p_i / p_{i-1})

    Args:
        prices: Ordered list of prices (oldest to newest).
        return_type: Type of return to calculate.
        calculation_version: Calculation methodology version.

    Returns:
        List of returns (length = len(prices) - 1).

    Raises:
        ValueError: If fewer than 2 prices.
        ValueError: If return_type is not recognized.
    """
    if len(prices) < 2:
        raise ValueError(f"Need at least 2 prices to calculate returns, got {len(prices)}")

    if calculation_version != CalculationVersion.CALCULATION_V1:
        raise ValueError(f"Unsupported calculation version: {calculation_version}")

    returns: list[float] = []

    if return_type == "absolute":
        for i in range(1, len(prices)):
            returns.append(prices[i] - prices[i - 1])

    elif return_type == "percentage":
        for i in range(1, len(prices)):
            prev = prices[i - 1]
            if prev == 0.0:
                returns.append(0.0)
            else:
                returns.append((prices[i] - prev) / prev)

    elif return_type == "log":
        for i in range(1, len(prices)):
            prev = prices[i - 1]
            if prev <= 0.0 or prices[i] <= 0.0:
                returns.append(0.0)
            else:
                returns.append(math.log(prices[i] / prev))

    else:
        raise ValueError(f"Unrecognized return_type '{return_type}'. Expected 'absolute', 'percentage', or 'log'.")

    return returns


def regression_slope(y: list[float]) -> float:
    """Least-squares slope of ``y`` vs the implicit index x = 0..n-1.

    Mirrors ``quant::statistics::Regression::slope`` (C++ OLS, O(n)) so the
    Python reference is numerically equivalent to the accelerated C++ path.

    Raises:
        ValueError: If ``y`` has fewer than 2 finite observations.
    """
    if len(y) < 2:
        raise ValueError("need at least 2 observations for regression slope")
    if any(not math.isfinite(v) for v in y):
        raise ValueError("series contains NaN or Inf")
    n = len(y)
    xbar = (n - 1.0) / 2.0
    ybar = sum(y) / n
    sxy = 0.0
    sxx = 0.0
    for i, yi in enumerate(y):
        dx = float(i) - xbar
        dy = yi - ybar
        sxy += dx * dy
        sxx += dx * dx
    if sxx == 0.0:
        raise ValueError("zero x variance (degenerate index)")
    return sxy / sxx


def regression_intercept(y: list[float]) -> float:
    """Least-squares intercept of ``y`` vs the implicit index x = 0..n-1.

    Mirrors ``quant::statistics::Regression::intercept`` (C++ OLS, O(n)).
    """
    if len(y) < 2:
        raise ValueError("need at least 2 observations for regression intercept")
    if any(not math.isfinite(v) for v in y):
        raise ValueError("series contains NaN or Inf")
    n = len(y)
    xbar = (n - 1.0) / 2.0
    ybar = sum(y) / n
    sxy = 0.0
    sxx = 0.0
    for i, yi in enumerate(y):
        dx = float(i) - xbar
        dy = yi - ybar
        sxy += dx * dy
        sxx += dx * dx
    if sxx == 0.0:
        raise ValueError("zero x variance (degenerate index)")
    beta = sxy / sxx
    return ybar - beta * xbar


def _regression_accumulate(x: list[float], y: list[float]) -> Any:
    """One-pass OLS sufficient statistics (mirrors C++ ``accumulate``)."""
    n = len(x)
    sum_x = sum(x)
    sum_y = sum(y)
    xbar = sum_x / n
    ybar = sum_y / n
    sxx = 0.0
    syy = 0.0
    sxy = 0.0
    for xi, yi in zip(x, y):
        dx = xi - xbar
        dy = yi - ybar
        sxx += dx * dx
        syy += dy * dy
        sxy += dx * dy
    return {"xbar": xbar, "ybar": ybar, "sxx": sxx, "syy": syy, "sxy": sxy}


def _validate_pair(x: list[float], y: list[float]) -> None:
    if len(x) != len(y):
        raise ValueError("x and y size mismatch")
    if len(x) < 2:
        raise ValueError("need at least 2 observations for regression")
    if any(not math.isfinite(v) for v in x) or any(not math.isfinite(v) for v in y):
        raise ValueError("series contains NaN or Inf")


def regression_correlation(x: list[float], y: list[float]) -> float:
    """Pearson correlation coefficient between ``x`` and ``y``.

    Mirrors ``quant::statistics::Regression::correlation`` (C++ OLS, O(n)).
    """
    _validate_pair(x, y)
    s = _regression_accumulate(x, y)
    if s["sxx"] == 0.0 or s["syy"] == 0.0:
        raise ValueError("zero variance in x or y")
    r = s["sxy"] / math.sqrt(s["sxx"] * s["syy"])
    return max(-1.0, min(1.0, r))


def regression_r_squared(x: list[float], y: list[float]) -> float:
    """Coefficient of determination R^2 = r^2 for the (x, y) fit.

    Mirrors ``quant::statistics::Regression::r_squared`` (C++ OLS, O(n)).
    """
    _validate_pair(x, y)
    s = _regression_accumulate(x, y)
    if s["sxx"] == 0.0 or s["syy"] == 0.0:
        raise ValueError("zero variance in x or y")
    r = s["sxy"] / math.sqrt(s["sxx"] * s["syy"])
    clamped = max(-1.0, min(1.0, r))
    return clamped * clamped


def regression_standard_error(x: list[float], y: list[float]) -> float:
    """Residual standard error of the (x, y) least-squares fit.

    Mirrors ``quant::statistics::Regression::standard_error`` (C++ OLS, O(n)).
    """
    _validate_pair(x, y)
    s = _regression_accumulate(x, y)
    if s["sxx"] == 0.0:
        raise ValueError("zero x variance")
    beta = s["sxy"] / s["sxx"]
    intercept_val = s["ybar"] - beta * s["xbar"]
    n = len(x)
    sse = 0.0
    for xi, yi in zip(x, y):
        e = yi - (intercept_val + beta * xi)
        sse += e * e
    return math.sqrt(sse / (n - 2.0))


def rolling_mean(data: list[float], window: int) -> list[float]:
    """Rolling arithmetic mean over a sliding window.

    Mirrors ``quant::RollingWindow::mean`` (C++ O(n) incremental).  Output
    length is ``len(data) - window + 1``.

    Raises:
        ValueError: If window <= 0 or window > len(data).
    """
    if window <= 0:
        raise ValueError("window must be > 0")
    if len(data) < window:
        raise ValueError("window size exceeds data length")
    n = len(data)
    out: list[float] = []
    s = sum(data[:window])
    out.append(s / window)
    for i in range(window, n):
        s += data[i]
        s -= data[i - window]
        out.append(s / window)
    return out


def rolling_volatility_incremental(data: list[float], window: int, ddof: int = 1) -> list[float]:
    """Rolling volatility (standard deviation) over a sliding window.

    Mirrors ``quant::RollingWindow::volatility`` (C++ O(n) incremental one-pass
    running-sum / running-sum-of-squares formulation).  Output length is
    ``len(data) - window + 1``.

    This mirrors the C++ accelerator exactly, including its scale-relative
    epsilon clamp, so the Python reference is numerically equivalent to the
    accelerated path (unlike the two-pass ``rolling_volatility`` helper above,
    which uses a different formula).

    Raises:
        ValueError: If window <= 0, window > len(data), or ddof not in [0, window).
    """
    if window <= 0:
        raise ValueError("window must be > 0")
    if len(data) < window:
        raise ValueError("window size exceeds data length")
    if ddof < 0 or ddof >= window:
        raise ValueError("ddof must be in [0, window)")
    n = len(data)
    denom = float(window - ddof)
    out: list[float] = []
    s = 0.0
    s2 = 0.0
    for i in range(window):
        s += data[i]
        s2 += data[i] * data[i]
    eps = 2.220446049250313e-16  # std::numeric_limits<double>::epsilon()

    def vol_of(cur_s: float, cur_s2: float) -> float:
        numerator = cur_s2 - cur_s * cur_s / window
        scale = cur_s2 + (cur_s * cur_s / window)
        if scale > 0.0 and numerator <= eps * 8.0 * scale:
            return 0.0
        var = numerator / denom
        return math.sqrt(var) if var > 0.0 else 0.0

    out.append(vol_of(s, s2))
    for i in range(window, n):
        s += data[i]
        s2 += data[i] * data[i]
        s -= data[i - window]
        s2 -= data[i - window] * data[i - window]
        out.append(vol_of(s, s2))
    return out


def rolling_variance_incremental(data: list[float], window: int, ddof: int = 1) -> list[float]:
    """Rolling variance over a sliding window.

    Mirrors ``quant::RollingWindow::variance`` (C++ O(n) incremental one-pass
    running-sum / running-sum-of-squares formulation).  Output length is
    ``len(data) - window + 1``.

    This mirrors the C++ accelerator exactly, including its scale-relative
    epsilon clamp, so the Python reference is numerically equivalent to the
    accelerated path (the variance is the square of the rolling volatility).

    Raises:
        ValueError: If window <= 0, window > len(data), or ddof not in [0, window).
    """
    if window <= 0:
        raise ValueError("window must be > 0")
    if len(data) < window:
        raise ValueError("window size exceeds data length")
    if ddof < 0 or ddof >= window:
        raise ValueError("ddof must be in [0, window)")
    n = len(data)
    denom = float(window - ddof)
    out: list[float] = []
    s = 0.0
    s2 = 0.0
    for i in range(window):
        s += data[i]
        s2 += data[i] * data[i]
    eps = 2.220446049250313e-16  # std::numeric_limits<double>::epsilon()

    def var_of(cur_s: float, cur_s2: float) -> float:
        numerator = cur_s2 - cur_s * cur_s / window
        scale = cur_s2 + (cur_s * cur_s / window)
        if scale > 0.0 and numerator <= eps * 8.0 * scale:
            return 0.0
        var = numerator / denom
        return var if var > 0.0 else 0.0

    out.append(var_of(s, s2))
    for i in range(window, n):
        s += data[i]
        s2 += data[i] * data[i]
        s -= data[i - window]
        s2 -= data[i - window] * data[i - window]
        out.append(var_of(s, s2))
    return out


def compute_statistics(
    returns: list[float],
    calculation_version: CalculationVersion = CalculationVersion.CALCULATION_V1,
) -> dict[str, Any]:
    """
    Calculate a comprehensive set of statistical summaries.

    Args:
        returns: List of periodic returns.
        calculation_version: Calculation methodology version.

    Returns:
        Dict with keys: mean, std, variance, skewness, kurtosis, min, max, count, sum.

    Raises:
        ValueError: If returns is empty.
    """
    _validate_returns(returns, min_samples=1)

    if calculation_version != CalculationVersion.CALCULATION_V1:
        raise ValueError(f"Unsupported calculation version: {calculation_version}")

    n = len(returns)
    result: dict[str, Any] = {
        "count": n,
        "sum": sum(returns),
        "mean": mean(returns),
        "min": min(returns),
        "max": max(returns),
    }

    if n >= 2:
        result["variance"] = variance(returns, ddof=1)
        result["std"] = standard_deviation(returns, ddof=1)
    else:
        result["variance"] = 0.0
        result["std"] = 0.0

    if n >= 3:
        result["skewness"] = skewness(returns)
    else:
        result["skewness"] = 0.0

    if n >= 4:
        result["kurtosis"] = kurtosis(returns, excess=True)
    else:
        result["kurtosis"] = 0.0

    return result
