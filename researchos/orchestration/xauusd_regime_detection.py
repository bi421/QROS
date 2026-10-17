"""Additive, point-in-time three-state XAUUSD market-regime research engine.

The classifier is a heuristic state label; Markov rows are empirical transition
frequencies, not calibrated forecasts or evidence of trading edge.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

STATES = ("UP", "DOWN", "RANGE")


def _hurst_variance_time(values: np.ndarray, max_lag: int = 20) -> float | None:
    """Estimate H from log variance of lagged differences; diagnostic only."""
    if len(values) < max(40, max_lag * 2) or not np.isfinite(values).all():
        return None
    lags = np.unique(np.geomspace(2, min(max_lag, len(values) // 2), 8).astype(int))
    points: list[tuple[float, float]] = []
    for lag in lags:
        diff = values[lag:] - values[:-lag]
        variance = float(np.var(diff))
        if variance > 0 and math.isfinite(variance):
            points.append((math.log(float(lag)), math.log(variance)))
    if len(points) < 4:
        return None
    slope = float(np.polyfit([p[0] for p in points], [p[1] for p in points], 1)[0])
    estimate = slope / 2.0
    return estimate if math.isfinite(estimate) else None


def _adx_and_di(frame: pd.DataFrame, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    high, low, close = (frame[name].astype(float) for name in ("high", "low", "close"))
    previous_close = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    atr = true_range.rolling(period, min_periods=period).mean()
    plus_di = 100.0 * plus_dm.rolling(period, min_periods=period).mean() / atr.replace(0, np.nan)
    minus_di = 100.0 * minus_dm.rolling(period, min_periods=period).mean() / atr.replace(0, np.nan)
    denominator = (plus_di + minus_di).replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / denominator
    adx = dx.rolling(period, min_periods=period).mean()
    return adx, plus_di, minus_di


def detect_market_regime(
    candles: pd.DataFrame,
    *,
    lookback: int = 100,
    adx_period: int = 14,
    range_adx: float = 20.0,
    trend_adx: float = 25.0,
    slope_floor: float = 0.05,
    dirichlet_alpha: float = 1.0,
    include_history: bool = False,
) -> dict[str, object]:
    """Classify latest candle and estimate next-state frequencies from past labels.

    Required columns: high, low, close. Rows must be chronological, unique,
    finite, and represent completed candles. This function does not fetch data.
    """
    if lookback < 40 or adx_period < 2:
        raise ValueError("lookback must be >= 40 and adx_period >= 2")
    if not (0 <= range_adx < trend_adx) or slope_floor < 0:
        raise ValueError("invalid regime thresholds")
    if not math.isfinite(dirichlet_alpha) or dirichlet_alpha <= 0:
        raise ValueError("dirichlet_alpha must be finite and positive")
    required = ("high", "low", "close")
    if not isinstance(candles, pd.DataFrame) or any(c not in candles for c in required):
        raise ValueError("candles must be a DataFrame with high, low, close")
    frame = candles.loc[:, required].copy()
    if len(frame) < max(lookback, adx_period * 2 + 2):
        raise ValueError("INSUFFICIENT_HISTORY")
    values = frame.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("OHLC values must be finite and positive")
    if (frame["high"] < frame[["low", "close"]].max(axis=1)).any() or (
        frame["low"] > frame[["high", "close"]].min(axis=1)
    ).any():
        raise ValueError("invalid OHLC candle geometry")

    log_close = np.log(frame["close"])
    adx, plus_di, minus_di = _adx_and_di(frame, adx_period)
    labels: list[str | None] = [None] * len(frame)
    hurst_values: list[float | None] = [None] * len(frame)
    slopes: list[float | None] = [None] * len(frame)

    for i in range(max(lookback - 1, adx_period * 2), len(frame)):
        start = i - lookback + 1
        window = log_close.iloc[start : i + 1].to_numpy()
        x = np.arange(len(window), dtype=float)
        slope = float(np.polyfit(x, window, 1)[0])
        return_scale = float(np.std(np.diff(window)))
        slope_per_bar = slope / return_scale if return_scale > 0 else 0.0
        hurst = _hurst_variance_time(window)
        slopes[i] = slope_per_bar
        hurst_values[i] = hurst
        strength = adx.iloc[i]
        pdi, mdi = plus_di.iloc[i], minus_di.iloc[i]
        if not all(math.isfinite(float(v)) for v in (strength, pdi, mdi, slope_per_bar)):
            continue
        # ADX measures strength, not direction; DI and price slope set direction.
        if strength >= trend_adx and slope_per_bar > slope_floor and pdi > mdi:
            labels[i] = "UP"
        elif strength >= trend_adx and slope_per_bar < -slope_floor and mdi > pdi:
            labels[i] = "DOWN"
        elif strength < range_adx or abs(slope_per_bar) <= slope_floor:
            labels[i] = "RANGE"
        else:
            # Ambiguous/transitioning observations are not forced into a trend.
            labels[i] = "RANGE"

    valid_positions = [i for i, label in enumerate(labels) if label is not None]
    if not valid_positions or valid_positions[-1] != len(frame) - 1:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "current_state": None,
            "state_probabilities_next": None,
            "probability_status": "NOT_ESTIMATED",
            "reason": "LATEST_CANDLE_NOT_CLASSIFIABLE",
            "execution_enabled": False,
        }

    counts = {state: {next_state: dirichlet_alpha for next_state in STATES} for state in STATES}
    transitions = 0
    for previous, current in zip(labels, labels[1:]):
        if previous in STATES and current in STATES:
            counts[previous][current] += 1
            transitions += 1
    current_state = labels[-1]
    row = counts[current_state]
    total = float(sum(row.values()))
    probabilities = {state: row[state] / total for state in STATES}
    current_hurst = hurst_values[-1]
    current_slope = slopes[-1]
    return {
        "status": "CLASSIFIED",
        "instrument": "XAUUSD",
        "current_state": current_state,
        "historical_states": labels if include_history else None,
        "features": {
            "adx": float(adx.iloc[-1]),
            "plus_di": float(plus_di.iloc[-1]),
            "minus_di": float(minus_di.iloc[-1]),
            "normalized_log_price_slope": current_slope,
            "hurst_variance_time": current_hurst,
        },
        "state_probabilities_next": probabilities,
        "transition_counts_with_prior": counts,
        "historical_transition_count": transitions,
        "probability_status": "SMOOTHED_EMPIRICAL_FREQUENCY_NOT_CALIBRATED",
        "method_notes": [
            "ADX measures trend strength, not direction.",
            "Hurst is a noisy diagnostic feature, not a standalone state label.",
            "Probabilities are smoothed historical state-transition frequencies.",
            "Validate walk-forward and on a separate holdout before forecasting claims.",
        ],
        "execution_enabled": False,
    }


__all__ = ["STATES", "detect_market_regime"]
