"""Statistical evidence primitives for Market Memory.

These functions keep descriptive statistics separate from inferential claims.
All calculations are deterministic and contain explicit sample-size guards.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ProportionEvidence:
    """Evidence for a binary outcome probability."""

    successes: int
    trials: int
    probability: float
    confidence_interval: Tuple[float, float]
    confidence_level: float = 0.95
    method: str = "wilson_score"

    @property
    def excludes_half(self) -> bool:
        """Whether the CI excludes 0.5 (descriptive, not causal)."""
        return self.confidence_interval[0] > 0.5 or self.confidence_interval[1] < 0.5


def wilson_proportion_ci(
    successes: int,
    trials: int,
    confidence_level: float = 0.95,
) -> ProportionEvidence:
    """Compute a Wilson score interval for a binomial proportion."""
    if trials < 1:
        raise ValueError("trials must be >= 1")
    if successes < 0 or successes > trials:
        raise ValueError("successes must be between 0 and trials")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be strictly between 0 and 1")

    z = _normal_quantile(0.5 + confidence_level / 2.0)
    p = successes / trials
    z2 = z * z
    denominator = 1.0 + z2 / trials
    centre = (p + z2 / (2.0 * trials)) / denominator
    half_width = z * math.sqrt(
        p * (1.0 - p) / trials + z2 / (4.0 * trials * trials)
    ) / denominator
    return ProportionEvidence(
        successes=successes,
        trials=trials,
        probability=p,
        confidence_interval=(
            max(0.0, centre - half_width),
            min(1.0, centre + half_width),
        ),
        confidence_level=confidence_level,
    )


def bonferroni_alpha(alpha: float, hypotheses: int) -> float:
    """Return the family-wise-error adjusted per-test alpha."""
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be strictly between 0 and 1")
    if hypotheses < 1:
        raise ValueError("hypotheses must be >= 1")
    return alpha / hypotheses


def _normal_quantile(p: float) -> float:
    """Return an Acklam-style deterministic inverse normal CDF approximation."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be strictly between 0 and 1")

    a = (
        -39.6968302866538,
        220.946098424521,
        -275.928510446969,
        138.357751867269,
        -30.6647980661472,
        2.50662827745924,
    )
    b = (
        -54.4760987982241,
        161.585836858041,
        -155.698979859887,
        66.8013118877197,
        -13.2806815528857,
    )
    c = (
        -0.00778489400243029,
        -0.322396458041136,
        -2.40075827716184,
        -2.54973253934373,
        4.37466414146497,
        2.93816398269878,
    )
    d = (
        0.00778469570904146,
        0.32246712907004,
        2.445134137143,
        3.75440866190742,
    )
    plow = 0.02425
    phigh = 1.0 - plow

    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        numerator = (
            (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q) + c[5]
        )
        denominator = ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q) + 1.0
        return numerator / denominator

    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        numerator = (
            (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q) + c[5]
        )
        denominator = ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q) + 1.0
        return -numerator / denominator

    q = p - 0.5
    r = q * q
    numerator = (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r) + a[5]
    ) * q
    denominator = (
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r) + 1.0
    )
    return numerator / denominator


__all__ = ["ProportionEvidence", "wilson_proportion_ci", "bonferroni_alpha"]
