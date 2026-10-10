"""Independent replay audit for the current market-geometry contract.

This verifies the declared arithmetic from ordered prices; it does not prove
that geometric features predict future market behavior.
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


def audit_market_geometry(
    prices: Sequence[float],
    measurement: Mapping[str, Any],
    *,
    tolerance: float = 1e-9,
) -> MathematicalAudit:
    """Recompute market-geometry outputs without calling production geometry."""
    try:
        values = [_number(value, "price") for value in prices]
        if len(values) < 2:
            raise ValueError("at least two finite prices are required")
        n = len(values)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("prices must be finite")

        x_mean = (n - 1) / 2.0
        y_mean = math.fsum(values) / n
        sxx = math.fsum((i - x_mean) ** 2 for i in range(n))
        syy = math.fsum((value - y_mean) ** 2 for value in values)
        sxy = math.fsum((i - x_mean) * (value - y_mean) for i, value in enumerate(values))
        slope = 0.0 if sxx == 0.0 else sxy / sxx
        intercept = y_mean - slope * x_mean
        residual = math.fsum(
            (value - (intercept + slope * i)) ** 2
            for i, value in enumerate(values)
        )
        r2 = (
            1.0 if syy == 0.0 and residual == 0.0
            else 0.0 if syy == 0.0
            else max(0.0, 1.0 - residual / syy)
        )

        dx = float(n - 1)
        dy = values[-1] - values[0]
        angle = math.atan2(dy, dx)
        distance = math.hypot(dx, dy)
        if n < 3:
            curvature = 0.0
        else:
            ax, ay = float(n - 3), values[-3]
            bx, by = float(n - 2), values[-2]
            cx, cy = float(n - 1), values[-1]
            abx, aby = bx - ax, by - ay
            bcx, bcy = cx - bx, cy - by
            acx, acy = cx - ax, cy - ay
            denominator = math.hypot(abx, aby) * math.hypot(bcx, bcy) * math.hypot(acx, acy)
            curvature = 0.0 if denominator == 0.0 else 2.0 * (abx * acy - aby * acx) / denominator

        pivot_lows = [
            values[i] for i in range(1, n - 1)
            if values[i] <= values[i - 1] and values[i] <= values[i + 1]
        ]
        pivot_highs = [
            values[i] for i in range(1, n - 1)
            if values[i] >= values[i - 1] and values[i] >= values[i + 1]
        ]
        support = math.fsum(pivot_lows) / len(pivot_lows) if pivot_lows else None
        resistance = math.fsum(pivot_highs) / len(pivot_highs) if pivot_highs else None

        reported = {
            "slope": _number(measurement["slope"], "slope"),
            "angle_radians": _number(measurement["angle_radians"], "angle_radians"),
            "angle_degrees": _number(measurement["angle_degrees"], "angle_degrees"),
            "distance": _number(measurement["distance"], "distance"),
            "vector_x": _number(measurement["vector"]["x"], "vector.x"),
            "vector_y": _number(measurement["vector"]["y"], "vector.y"),
            "curvature": _number(measurement["curvature"], "curvature"),
            "trend_r2": _number(measurement["trend_r2"], "trend_r2"),
        }
        expected = {
            "slope": slope,
            "angle_radians": angle,
            "angle_degrees": math.degrees(angle),
            "distance": distance,
            "vector_x": dx,
            "vector_y": dy,
            "curvature": curvature,
            "trend_r2": r2,
        }
        for name, value in (("support_level", support), ("resistance_level", resistance)):
            actual = measurement.get(name)
            if value is None:
                if actual is not None:
                    raise ValueError(f"{name} should be null when no pivots exist")
            else:
                reported[name] = _number(actual, name)
                expected[name] = value
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return MathematicalAudit(
            "market_geometry",
            AuditStatus.INVALID_INPUT,
            "geometry replay inputs",
            None,
            None,
            None,
            tolerance,
            (),
            f"Cannot independently verify market geometry: {exc}",
        )

    errors = {name: abs(expected[name] - reported[name]) for name in expected}
    worst = max(errors, key=errors.get)
    status = AuditStatus.VERIFIED if all(error <= tolerance for error in errors.values()) else AuditStatus.FALSIFIED
    return MathematicalAudit(
        "market_geometry",
        status,
        worst,
        expected[worst],
        reported[worst],
        errors[worst],
        tolerance,
        (
            "prices are the exact ordered observations used by the engine",
            "trend regression uses zero-based sequential observation indices",
            "support and resistance are means of local three-point pivots",
        ),
        (
            "All audited geometry fields match an independent recomputation. This is arithmetic verification only."
            if status is AuditStatus.VERIFIED
            else f"Independent recomputation contradicts geometry field {worst}; the numerical claim is falsified."
        ),
    )
