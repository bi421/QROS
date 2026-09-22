"""
Label Generation Engine — label functions.

Deterministic, pure-Python generators for supervised-learning targets.

Design rules:
    * No randomness.
    * No numpy / pandas / sklearn / ML libraries.
    * No broker logic and no trading execution.
    * No NaN values are ever emitted (missing values are represented with
      ``None``).
    * Labels at index ``i`` intentionally use future information (they are
      forward-looking supervised targets) and nothing else.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _sanitize(values: Iterable[object]) -> list[float | None]:
    """Convert inputs to floats; map missing / non-finite values to ``None``."""
    out: list[float | None] = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            out.append(None)
            continue
        if math.isnan(f) or math.isinf(f):
            out.append(None)
        else:
            out.append(f)
    return out


def _check_horizon(horizon: int) -> None:
    """Validate that ``horizon`` is a positive integer."""
    if isinstance(horizon, bool) or not isinstance(horizon, int):
        raise ValueError("horizon must be an integer")
    if horizon <= 0:
        raise ValueError("horizon must be a positive integer")


def _check_threshold(threshold: float) -> None:
    """Validate that ``threshold`` is a finite, non-negative number."""
    f = float(threshold)
    if math.isnan(f) or math.isinf(f) or f < 0:
        raise ValueError("threshold must be a non-negative number")


def _check_positive(value: float, name: str) -> None:
    """Validate that ``value`` is a finite, positive number."""
    f = float(value)
    if math.isnan(f) or math.isinf(f) or f <= 0:
        raise ValueError(f"{name} must be a positive number")


# ---------------------------------------------------------------------------
# future return
# ---------------------------------------------------------------------------


def future_return(close: Iterable[object], horizon: int) -> list[float | None]:
    """Forward-return label.

    ``label[i] = (close[i + horizon] - close[i]) / close[i]``

    The last ``horizon`` observations are ``None`` because their forward
    window is incomplete.  A zero base price yields ``None``.
    """
    _check_horizon(horizon)
    close = _sanitize(close)
    n = len(close)
    out: list[float | None] = [None] * n
    for i in range(n - horizon):
        base = close[i]
        if base is None or base == 0:
            continue
        forward = close[i + horizon]
        if forward is None:
            continue
        out[i] = (forward - base) / base
    return out


# ---------------------------------------------------------------------------
# binary direction
# ---------------------------------------------------------------------------


def binary_label(close: Iterable[object], horizon: int) -> list[int | None]:
    """Binary direction label.

    ``1`` if future return > 0, else ``0``.
    """
    returns = future_return(close, horizon)
    out: list[int | None] = []
    for v in returns:
        if v is None:
            out.append(None)
        elif v > 0:
            out.append(1)
        else:
            out.append(0)
    return out


# ---------------------------------------------------------------------------
# multi-class direction
# ---------------------------------------------------------------------------


def multiclass_label(close: Iterable[object], horizon: int, threshold: float) -> list[int | None]:
    """Multi-class direction label.

    ``1``  up      (future return > threshold)
    ``0``  neutral (|future return| <= threshold)
    ``-1`` down    (future return < -threshold)
    """
    _check_threshold(threshold)
    returns = future_return(close, horizon)
    out: list[int | None] = []
    for v in returns:
        if v is None:
            out.append(None)
        elif v > threshold:
            out.append(1)
        elif v < -threshold:
            out.append(-1)
        else:
            out.append(0)
    return out


# ---------------------------------------------------------------------------
# regression target
# ---------------------------------------------------------------------------


def regression_target(close: Iterable[object], horizon: int) -> list[float | None]:
    """Regression target — alias of :func:`future_return`."""
    return future_return(close, horizon)


# ---------------------------------------------------------------------------
# triple barrier
# ---------------------------------------------------------------------------


def triple_barrier(
    close: Iterable[object],
    take_profit: float,
    stop_loss: float,
    max_horizon: int,
) -> list[int | None]:
    """Simplified deterministic triple-barrier label.

    Scans forward from each bar for up to ``max_horizon`` bars:

    ``1``  take profit reached first
    ``-1`` stop loss reached first
    ``0``  neither barrier reached within ``max_horizon`` bars

    Bars without a full forward window (``i + max_horizon >= n``) are
    ``None`` because the outcome is unknown.
    """
    _check_positive(take_profit, "take_profit")
    _check_positive(stop_loss, "stop_loss")
    _check_horizon(max_horizon)
    close = _sanitize(close)
    n = len(close)
    out: list[int | None] = [None] * n
    for i in range(n):
        end = i + max_horizon
        if end >= n:
            continue
        entry = close[i]
        if entry is None or entry == 0:
            continue
        label: int = 0
        for j in range(i + 1, end + 1):
            value = close[j]
            if value is None:
                break
            ret = (value - entry) / entry
            if ret >= take_profit:
                label = 1
                break
            if ret <= -stop_loss:
                label = -1
                break
        out[i] = label
    return out


# ---------------------------------------------------------------------------
# volatility adjusted return
# ---------------------------------------------------------------------------


def vol_adjusted_return(
    close: Iterable[object],
    rolling_volatility: Iterable[object],
    horizon: int,
) -> list[float | None]:
    """Volatility-adjusted forward return.

    ``future_return / rolling_volatility``.

    Returns ``None`` when the future return is undefined, or the volatility
    is missing or zero (avoids divide-by-zero).
    """
    returns = future_return(close, horizon)
    vol = _sanitize(rolling_volatility)
    n = len(returns)
    out: list[float | None] = [None] * n
    for i in range(n):
        ret = returns[i]
        if ret is None:
            continue
        if i >= len(vol):
            continue
        v = vol[i]
        if v is None or v == 0:
            continue
        out[i] = ret / v
    return out


__all__ = [
    "binary_label",
    "future_return",
    "multiclass_label",
    "regression_target",
    "triple_barrier",
    "vol_adjusted_return",
]
