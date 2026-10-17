"""Causal volatility/session gates for XAUUSD research-only signal selection."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Sequence


def classify_session(timestamp: datetime) -> str:
    """UTC session bucket; caller must convert timestamps to verified UTC first.

    Simplified fixed UTC buckets are a proxy, not an exchange-calendar model.
    """
    hour = timestamp.hour
    if 0 <= hour < 7:
        return "ASIA"
    if 7 <= hour < 13:
        return "LONDON"
    if 13 <= hour < 22:
        return "NEW_YORK_OVERLAP"
    return "ROLLOVER"


def volatility_gate(
    prior_true_ranges: Sequence[float],
    current_true_range: float,
    *,
    min_history: int = 50,
    percentile_floor: float = 0.60,
) -> dict[str, float | bool | str | None]:
    """Use only prior ranges to decide if current range is high-volatility.

    Empirical percentile uses strict prior history and an inclusive rank. The
    percentile floor must be declared before evaluating a final holdout.
    """
    if isinstance(min_history, bool) or not isinstance(min_history, int) or min_history < 2:
        raise ValueError("min_history must be an integer >= 2")
    if not math.isfinite(percentile_floor) or not 0.0 <= percentile_floor <= 1.0:
        raise ValueError("percentile_floor must be within [0, 1]")
    values = [float(x) for x in prior_true_ranges]
    if any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError("prior true ranges must be finite and nonnegative")
    current = float(current_true_range)
    if not math.isfinite(current) or current < 0:
        raise ValueError("current_true_range must be finite and nonnegative")
    if len(values) < min_history:
        return {"eligible": False, "percentile": None, "threshold": None, "status": "WARMUP"}
    sorted_prior = sorted(values)
    rank = sum(x <= current for x in sorted_prior) / len(sorted_prior)
    threshold_index = min(
        len(sorted_prior) - 1, max(0, math.ceil(percentile_floor * len(sorted_prior)) - 1)
    )
    threshold = sorted_prior[threshold_index]
    return {
        "eligible": rank >= percentile_floor,
        "percentile": rank,
        "threshold": threshold,
        "status": "HIGH_VOLATILITY" if rank >= percentile_floor else "LOW_OR_MID_VOLATILITY",
    }


def speed_curvature_interaction(speed_z: float, curvature: float | None) -> float | None:
    """Bounded interaction proxy; inputs must be causal and standardized on TRAIN only."""
    if not math.isfinite(speed_z):
        raise ValueError("speed_z must be finite")
    if curvature is None:
        return None
    if not math.isfinite(curvature):
        raise ValueError("curvature must be finite or None")
    return speed_z * curvature


__all__ = ["classify_session", "volatility_gate", "speed_curvature_interaction"]
