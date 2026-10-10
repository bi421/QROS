"""Independent replay audit for descriptive statistics on raw price observations.

This checks numerical outputs, not statistical assumptions or predictive validity.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from researchos.quant_engine.mathematical_falsification import (
    AuditStatus,
    MathematicalAudit,
    _number,
)


def audit_descriptive_statistics(
    prices: Sequence[float],
    measurement: Mapping[str, Any],
    *,
    tolerance: float = 1e-9,
) -> MathematicalAudit:
    """Recompute descriptive statistics independently from raw prices."""
    try:
        values = [_number(value, "price") for value in prices]
        if len(values) < 2:
            raise ValueError("at least two finite observations are required")
        n = len(values)
        reported_count = _number(measurement["count"], "count")
        if not reported_count.is_integer() or int(reported_count) != n:
            raise ValueError("reported count does not match the input length")

        mean = math.fsum(values) / n
        centered = [value - mean for value in values]
        variance = math.fsum(delta * delta for delta in centered) / n
        sd = math.sqrt(variance)
        last_z = 0.0 if sd == 0.0 else centered[-1] / sd
        minimum, maximum = min(values), max(values)

        x_mean = (n - 1) / 2.0
        x_centered = [index - x_mean for index in range(n)]
        sxx = math.fsum(value * value for value in x_centered)
        syy = math.fsum(value * value for value in centered)
        sxy = math.fsum(x * y for x, y in zip(x_centered, centered))
        slope = 0.0 if sxx == 0.0 else sxy / sxx
        intercept = mean - slope * x_mean
        correlation = 0.0 if syy == 0.0 or sxx == 0.0 else sxy / math.sqrt(sxx * syy)
        residual = math.fsum(
            (values[index] - (intercept + slope * index)) ** 2
            for index in range(n)
        )
        r2 = (
            1.0
            if syy == 0.0 and residual == 0.0
            else 0.0
            if syy == 0.0
            else max(0.0, 1.0 - residual / syy)
        )

        expected = {
            "mean": mean,
            "variance": variance,
            "standard_deviation": sd,
            "minimum": minimum,
            "maximum": maximum,
            "z_score_last": last_z,
            "correlation": correlation,
            "regression_slope": slope,
            "regression_intercept": intercept,
            "regression_r2": r2,
        }
        reported = {
            key: _number(measurement[key], key)
            for key in expected
        }
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return MathematicalAudit(
            "descriptive_statistics",
            AuditStatus.INVALID_INPUT,
            "statistics replay inputs",
            None,
            None,
            None,
            tolerance,
            (),
            f"Cannot independently verify descriptive statistics: {exc}",
        )

    errors = {key: abs(expected[key] - reported[key]) for key in expected}
    worst = max(errors, key=errors.get)
    status = (
        AuditStatus.VERIFIED
        if all(error <= tolerance for error in errors.values())
        else AuditStatus.FALSIFIED
    )
    return MathematicalAudit(
        "descriptive_statistics",
        status,
        worst,
        expected[worst],
        reported[worst],
        errors[worst],
        tolerance,
        (
            "input values are the exact ordered observations used by the engine",
            "variance and standard deviation use the population convention",
            "regression uses sequential observation indices as x",
        ),
        (
            "All audited descriptive-statistic fields match an independent recomputation. "
            "This verifies arithmetic only, not distributional assumptions or market predictability."
            if status is AuditStatus.VERIFIED
            else f"Independent recomputation contradicts the reported {worst}; the numerical claim is falsified."
        ),
    )
