"""Deterministic probability calibration and uncertainty primitives."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class CalibrationResult:
    """Immutable calibration metrics with explicit sample-count provenance."""

    brier_score: float
    sample_size: int
    mean_predicted_probability: float
    observed_frequency: float

    def __post_init__(self) -> None:
        if self.sample_size < 1:
            raise ValueError("sample_size must be >= 1")
        for name in (
            "brier_score",
            "mean_predicted_probability",
            "observed_frequency",
        ):
            value = getattr(self, name)
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if not 0.0 <= self.brier_score <= 1.0:
            raise ValueError("brier_score must be in [0, 1]")
        if not 0.0 <= self.mean_predicted_probability <= 1.0:
            raise ValueError("mean_predicted_probability must be in [0, 1]")
        if not 0.0 <= self.observed_frequency <= 1.0:
            raise ValueError("observed_frequency must be in [0, 1]")


def brier_score(probabilities: Sequence[float], outcomes: Sequence[int | bool]) -> CalibrationResult:
    """Return the binary Brier score plus aggregate calibration diagnostics."""
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ValueError("probabilities and outcomes must have the same non-zero length")
    ps = [float(p) for p in probabilities]
    ys = [int(y) for y in outcomes]
    if any(not math.isfinite(p) or not 0.0 <= p <= 1.0 for p in ps):
        raise ValueError("probabilities must be finite and in [0, 1]")
    if any(y not in (0, 1) for y in ys):
        raise ValueError("outcomes must be binary 0/1")
    n = len(ps)
    return CalibrationResult(
        brier_score=math.fsum((p - y) ** 2 for p, y in zip(ps, ys, strict=True)) / n,
        sample_size=n,
        mean_predicted_probability=math.fsum(ps) / n,
        observed_frequency=math.fsum(ys) / n,
    )


def wilson_interval(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    """Return a deterministic Wilson score interval for a binomial proportion."""
    if trials < 1 or successes < 0 or successes > trials:
        raise ValueError("successes must be in [0, trials] and trials must be >= 1")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    z = _normal_quantile(0.5 + confidence / 2.0)
    phat = successes / trials
    denominator = 1.0 + z * z / trials
    centre = (phat + z * z / (2.0 * trials)) / denominator
    margin = z * math.sqrt((phat * (1.0 - phat) / trials) + (z * z / (4.0 * trials * trials))) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def _normal_quantile(p: float) -> float:
    """Acklam-style rational approximation for the standard normal quantile."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    a = (-39.69683028665376, 220.9460984245205, -275.9285104469687,
         138.3577518672690, -30.66479806614716, 2.506628277459239)
    b = (-54.47609879822406, 161.5858368580409, -155.6989798598866,
         66.80131188771972, -13.28068155288572)
    c = (-0.007784894002430293, -0.3223964580411365, -2.400758277161838,
         -2.549732539343734, 4.374664141464968, 2.938163982698783)
    d = (0.007784695709041462, 0.3224671290700398, 2.445134137142996,
         3.754408661907416)
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
                ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0))
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
                 ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0))
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q) /            (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + b[5]) * r + 1.0)
