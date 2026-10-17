"""Dependency-aware diagnostics and multiple-testing correction for research audits.

ESS is an AR(1)-style approximation, not a substitute for block bootstrap.
BH controls FDR under independence and common positive-dependence conditions;
corrected discoveries are not proof of economic or trading edge.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def lag_autocorrelation(values: Sequence[float]) -> float | None:
    """Return lag-1 Pearson autocorrelation, or None for degenerate samples."""
    n = len(values)
    if n < 3:
        return None
    mean = math.fsum(values) / n
    centered = [float(x) - mean for x in values]
    denom = math.fsum(x * x for x in centered)
    if denom <= 0.0:
        return None
    return math.fsum(centered[i] * centered[i - 1] for i in range(1, n)) / denom


def effective_sample_size(n: int, rho1: float | None) -> dict[str, int | float | str | None]:
    """Approximate ESS using an AR(1) lag-1 correction, capped to [1, n]."""
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError("n must be an integer >= 1")
    if rho1 is None or not math.isfinite(rho1):
        return {
            "n": n,
            "lag1_autocorrelation": rho1,
            "n_effective_approx": None,
            "method": "AR(1) lag-1 approximation; unavailable for degenerate series",
        }
    rho = min(0.999999, max(-0.999999, float(rho1)))
    estimate = n * (1.0 - rho) / (1.0 + rho)
    neff = max(1, min(n, int(round(estimate))))
    return {
        "n": n,
        "lag1_autocorrelation": rho1,
        "n_effective_approx": neff,
        "method": "AR(1) lag-1 approximation; diagnostic only, not an exact correction for general time series",
    }


def benjamini_hochberg(
    p_values: Sequence[float], q: float = 0.05
) -> list[dict[str, float | int | bool]]:
    """Return BH-adjusted p-values and rejection decisions in original order."""
    if not math.isfinite(q) or not 0.0 < q < 1.0:
        raise ValueError("q must be strictly between 0 and 1")
    vals = [float(p) for p in p_values]
    if any(not math.isfinite(p) or not 0.0 <= p <= 1.0 for p in vals):
        raise ValueError("all p-values must be finite and in [0, 1]")
    m = len(vals)
    if not m:
        return []
    order = sorted(range(m), key=lambda i: vals[i])
    adjusted = [1.0] * m
    running = 1.0
    for rank_index in range(m - 1, -1, -1):
        idx = order[rank_index]
        rank = rank_index + 1
        running = min(running, vals[idx] * m / rank)
        adjusted[idx] = min(1.0, running)
    return [
        {
            "p_value": vals[i],
            "p_adjusted_bh": adjusted[i],
            "rank": order.index(i) + 1,
            "reject_at_q": adjusted[i] <= q,
        }
        for i in range(m)
    ]


__all__ = ["lag_autocorrelation", "effective_sample_size", "benjamini_hochberg"]
