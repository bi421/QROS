"""Causal candle-velocity features for XAUUSD research.

This module measures completed OHLC candles only. It emits features, not a
trading recommendation; empirical outcome rates must be estimated separately
on chronologically held-out observations.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Literal, Sequence

Outcome = Literal["CONTINUATION", "REVERSAL", "SIDEWAYS"]


def _finite_positive(name: str, value: float) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return number


class CandleVelocityEngine:
    """O(1) rolling candle velocity with a strictly prior-window Z-score."""

    __slots__ = ("window", "z_threshold", "_ranges", "_sum", "_sum_sq", "_count")

    def __init__(self, window: int = 20, z_threshold: float = 2.0) -> None:
        if isinstance(window, bool) or not isinstance(window, int) or window < 2:
            raise ValueError("window must be an integer >= 2")
        if not math.isfinite(z_threshold) or z_threshold <= 0.0:
            raise ValueError("z_threshold must be finite and positive")
        self.window = window
        self.z_threshold = float(z_threshold)
        self._ranges: deque[float] = deque()
        self._sum = 0.0
        self._sum_sq = 0.0
        self._count = 0

    def update(
        self, open_: float, high: float, low: float, close: float, *, interval_seconds: float = 60.0
    ) -> dict[str, float | int | bool | None]:
        """Consume one completed candle; range and directional velocities are price/second."""
        o = _finite_positive("open", open_)
        h = _finite_positive("high", high)
        lo = _finite_positive("low", low)
        c = _finite_positive("close", close)
        dt = _finite_positive("interval_seconds", interval_seconds)
        if h < max(o, c, lo) or lo > min(o, c, h):
            raise ValueError("invalid OHLC ordering")

        raw_range = h - lo
        body = abs(c - o)
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - lo
        body_ratio = body / raw_range if raw_range > 0.0 else 0.0
        upper_wick_ratio = upper_wick / raw_range if raw_range > 0.0 else 0.0
        lower_wick_ratio = lower_wick / raw_range if raw_range > 0.0 else 0.0
        close_location = (c - lo) / raw_range if raw_range > 0.0 else 0.5
        range_velocity = raw_range / dt
        directional_velocity = (c - o) / dt
        z_score: float | None = None
        impulse = False
        if len(self._ranges) >= self.window:
            mean = self._sum / self.window
            variance = max(0.0, self._sum_sq / self.window - mean * mean)
            std = math.sqrt(variance)
            if std > 0.0:
                z_score = (range_velocity - mean) / std
                impulse = z_score >= self.z_threshold

        # Add this candle only after scoring it, preventing self-inclusion.
        if len(self._ranges) == self.window:
            expired = self._ranges.popleft()
            self._sum -= expired
            self._sum_sq -= expired * expired
        self._ranges.append(range_velocity)
        self._sum += range_velocity
        self._sum_sq += range_velocity * range_velocity
        self._count += 1

        direction = 1 if c > o else -1 if c < o else 0
        return {
            "bar_count": self._count,
            "direction": direction,
            "range_velocity": range_velocity,
            "directional_velocity": directional_velocity,
            "body_length": body,
            "upper_wick_length": upper_wick,
            "lower_wick_length": lower_wick,
            "body_ratio": body_ratio,
            "upper_wick_ratio": upper_wick_ratio,
            "lower_wick_ratio": lower_wick_ratio,
            "close_location": close_location,
            "wick_pattern": (
                "UPPER_WICK_DOMINANT"
                if upper_wick_ratio - lower_wick_ratio >= 0.15
                else "LOWER_WICK_DOMINANT"
                if lower_wick_ratio - upper_wick_ratio >= 0.15
                else "BALANCED"
            ),
            "z_speed": z_score,
            "impulse": impulse,
            "warmup_complete": z_score is not None,
        }


def estimate_conditional_outcomes(
    z_scores: Sequence[float | None],
    impulse_directions: Sequence[int],
    future_outcomes: Sequence[Outcome | None],
    *,
    z_threshold: float = 2.0,
) -> dict[str, object]:
    """Estimate observed continuation/reversal/sideways rates for eligible impulses.

    Inputs must be aligned chronologically. The caller is responsible for using
    only future outcomes fully observable at each event and for reporting the
    sample's date range and out-of-sample split. No smoothing or predictive claim
    is applied; empty samples return null probabilities.
    """
    if not (len(z_scores) == len(impulse_directions) == len(future_outcomes)):
        raise ValueError("input sequences must have equal lengths")
    if not math.isfinite(z_threshold) or z_threshold <= 0.0:
        raise ValueError("z_threshold must be finite and positive")
    counts = {name: 0 for name in ("CONTINUATION", "REVERSAL", "SIDEWAYS")}
    eligible = 0
    for z_score, direction, outcome in zip(z_scores, impulse_directions, future_outcomes):
        if z_score is None or not math.isfinite(z_score) or z_score < z_threshold:
            continue
        if direction not in (-1, 1) or outcome is None:
            continue
        if outcome not in counts:
            raise ValueError(f"unknown outcome: {outcome}")
        counts[outcome] += 1
        eligible += 1
    probabilities = {
        name: (count / eligible if eligible else None) for name, count in counts.items()
    }
    return {"eligible_events": eligible, "counts": counts, "probabilities": probabilities}


def estimate_wick_conditioned_outcomes(features, future_outcomes, *, z_threshold=2.0):
    """Report empirical outcomes grouped by impulse direction and wick pattern."""
    if len(features) != len(future_outcomes):
        raise ValueError("features and future_outcomes must have equal lengths")
    if not math.isfinite(z_threshold) or z_threshold <= 0.0:
        raise ValueError("z_threshold must be finite and positive")
    names = ("CONTINUATION", "REVERSAL", "SIDEWAYS")
    groups = {}
    for feature, outcome in zip(features, future_outcomes):
        z = feature.get("z_speed")
        direction = feature.get("direction")
        pattern = feature.get("wick_pattern")
        if z is None or not isinstance(z, (int, float)) or not math.isfinite(z) or z < z_threshold:
            continue
        if direction not in (-1, 1) or outcome is None:
            continue
        if outcome not in names:
            raise ValueError(f"unknown outcome: {outcome}")
        if pattern not in ("UPPER_WICK_DOMINANT", "LOWER_WICK_DOMINANT", "BALANCED"):
            continue
        key = f"direction_{'UP' if direction == 1 else 'DOWN'}|{pattern}"
        counts = groups.setdefault(key, {name: 0 for name in names})
        counts[outcome] += 1
    report = {}
    for key, counts in sorted(groups.items()):
        n = sum(counts.values())
        report[key] = {
            "n": n,
            "counts": counts,
            "probabilities": {name: counts[name] / n for name in names},
        }
    return {"z_threshold": z_threshold, "groups": report, "group_count": len(report)}


__all__ = [
    "CandleVelocityEngine",
    "Outcome",
    "estimate_conditional_outcomes",
    "estimate_wick_conditioned_outcomes",
]
