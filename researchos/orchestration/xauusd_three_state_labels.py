"""Direction-neutral OHLC triple-barrier labels for XAUUSD regime research.

Labels describe the first future barrier touched after the signal candle closes.
This is an offline target-labeling utility, not a predictor or execution path.
"""
from __future__ import annotations

import math
from typing import Literal, Sequence

from researchos.orchestration.xauusd_labels import OHLCBar

ThreeStateLabel = Literal["UP", "DOWN", "RANGE"]


def label_three_state_triple_barrier(
    bars: Sequence[OHLCBar],
    atr: Sequence[float | None],
    *,
    upper_atr: float = 1.0,
    lower_atr: float = 1.0,
    max_holding_bars: int = 16,
) -> list[ThreeStateLabel | None]:
    """Label each close using symmetric/asymmetric ATR barriers.

    Barrier levels are anchored at close[t], which is known at event time t.
    Scanning starts at bar t+1, so the target never uses the event candle's
    own high/low. A full forward window is required. If both barriers are
    touched in one candle, the event is excluded (None), since OHLC cannot
    reveal intrabar ordering. If neither barrier is touched by the vertical
    barrier, the result is RANGE. ATR must be computed using data available at t.
    """
    if len(bars) != len(atr):
        raise ValueError("bars and atr must have equal lengths")
    for previous, current in zip(bars, bars[1:]):
        if current.timestamp <= previous.timestamp:
            raise ValueError("bar timestamps must be strictly increasing")
    for name, value in (("upper_atr", upper_atr), ("lower_atr", lower_atr)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    if isinstance(max_holding_bars, bool) or not isinstance(max_holding_bars, int) or max_holding_bars < 1:
        raise ValueError("max_holding_bars must be a positive integer")

    normalized_atr: list[float | None] = []
    for value in atr:
        if value is None:
            normalized_atr.append(None)
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError("ATR values must be finite and positive or None")
        else:
            normalized_atr.append(float(value))

    labels: list[ThreeStateLabel | None] = [None] * len(bars)
    for i, bar in enumerate(bars):
        end = i + max_holding_bars
        event_atr = normalized_atr[i]
        if event_atr is None or end >= len(bars):
            continue
        upper = bar.close + upper_atr * event_atr
        lower = bar.close - lower_atr * event_atr
        resolved: ThreeStateLabel | None = None
        for j in range(i + 1, end + 1):
            future = bars[j]
            # A gap through a barrier is evidence of that barrier being reached.
            if future.open >= upper:
                resolved = "UP"
                break
            if future.open <= lower:
                resolved = "DOWN"
                break
            hit_up = future.high >= upper
            hit_down = future.low <= lower
            if hit_up and hit_down:
                resolved = None  # Intrabar ordering is unknowable from OHLC.
                break
            if hit_up:
                resolved = "UP"
                break
            if hit_down:
                resolved = "DOWN"
                break
            if j == end:
                resolved = "RANGE"
        labels[i] = resolved
    return labels


__all__ = ["ThreeStateLabel", "label_three_state_triple_barrier"]
