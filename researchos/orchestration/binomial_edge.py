"""Binomial edge tests for binary trading outcomes.

A binomial test is valid only for a defined binary event and a defensible null
probability. It does not by itself establish profitability or independence.
"""

from __future__ import annotations

import math


def binomial_edge_test(
    successes: int,
    trials: int,
    *,
    null_probability: float = 0.5,
    alternative: str = "greater",
    confidence: float = 0.95,
) -> dict[str, int | float | str | bool]:
    """Test whether a binary success rate differs from a specified null rate.

    Uses an exact binomial tail probability and a Wilson score confidence
    interval for the observed rate. ``greater`` tests success rate > null rate;
    ``less`` tests <; ``two-sided`` tests !=. Overlapping trading labels or
    serially dependent events violate the usual independent-trials assumption.
    """
    if isinstance(trials, bool) or not isinstance(trials, int) or trials < 1:
        raise ValueError("trials must be an integer >= 1")
    if (
        isinstance(successes, bool)
        or not isinstance(successes, int)
        or not 0 <= successes <= trials
    ):
        raise ValueError("successes must be an integer between 0 and trials")
    if not math.isfinite(null_probability) or not 0.0 < null_probability < 1.0:
        raise ValueError("null_probability must be strictly between 0 and 1")
    if alternative not in ("greater", "less", "two-sided"):
        raise ValueError("alternative must be greater, less, or two-sided")
    if not math.isfinite(confidence) or not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between 0 and 1")

    n, k, p0 = trials, successes, null_probability
    observed = k / n

    def log_pmf(x: int) -> float:
        return (
            math.lgamma(n + 1)
            - math.lgamma(x + 1)
            - math.lgamma(n - x + 1)
            + x * math.log(p0)
            + (n - x) * math.log1p(-p0)
        )

    logs = [log_pmf(x) for x in range(n + 1)]
    if alternative == "greater":
        p_value = math.fsum(math.exp(v) for v in logs[k:])
    elif alternative == "less":
        p_value = math.fsum(math.exp(v) for v in logs[: k + 1])
    else:
        observed_log_p = logs[k]
        p_value = math.fsum(math.exp(v) for v in logs if v <= observed_log_p + 1e-12)
    p_value = min(1.0, max(0.0, p_value))

    # Wilson score interval (normal approximation to the score statistic).
    # Common 90%, 95%, and 99% confidence levels are supported without SciPy.
    z_by_confidence = {0.90: 1.6448536269514722, 0.95: 1.959963984540054, 0.99: 2.5758293035489004}
    nearest = min(z_by_confidence, key=lambda c: abs(c - confidence))
    if abs(nearest - confidence) > 1e-9:
        raise ValueError("confidence must be one of 0.90, 0.95, or 0.99")
    z = z_by_confidence[nearest]
    denom = 1.0 + z * z / n
    center = (observed + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(observed * (1.0 - observed) / n + z * z / (4.0 * n * n)) / denom
    lower, upper = max(0.0, center - half), min(1.0, center + half)

    return {
        "successes": k,
        "trials": n,
        "observed_rate": observed,
        "null_probability": p0,
        "alternative": alternative,
        "exact_p_value": p_value,
        "confidence_level": confidence,
        "wilson_interval_lower": lower,
        "wilson_interval_upper": upper,
        "significant_at_0_05": p_value < 0.05,
        "reject_null_at_0_05": p_value < 0.05,
        "assumption_warning": "Requires a pre-defined binary outcome and approximately independent trials; overlapping horizons and serial dependence can overstate evidence.",
    }


__all__ = ["binomial_edge_test"]
