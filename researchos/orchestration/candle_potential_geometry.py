"""Causal potential-displacement and path-curvature features for OHLC research.

These are statistical proxies, not physical energy, force, or a validated market law.
"""

from __future__ import annotations
import math


def potential_geometry_features(
    *,
    close: float,
    ema: float,
    prior_log_returns: list[float],
    current_log_return: float,
    prior_return_scale: float,
    range_velocity: float,
    epsilon: float = 1e-12,
) -> dict[str, float | None]:
    """Return causal normalized displacement, energy ratio, and discrete curvature.

    `prior_log_returns` must contain only observations strictly before current bar.
    Curvature is a dimensionless finite-difference proxy on log-price per bar.
    """
    values = (close, ema, current_log_return, prior_return_scale, range_velocity, epsilon)
    if not all(math.isfinite(float(v)) for v in values):
        raise ValueError("inputs must be finite")
    if close <= 0 or ema <= 0 or prior_return_scale < 0 or range_velocity < 0 or epsilon <= 0:
        raise ValueError("prices must be positive; scales nonnegative; epsilon positive")
    displacement = math.log(close / ema)
    scale = max(prior_return_scale, epsilon)
    normalized_displacement = displacement / scale
    potential = 0.5 * normalized_displacement * normalized_displacement
    kinetic_proxy = 0.5 * (range_velocity / scale) ** 2
    energy_ratio = kinetic_proxy / max(potential, epsilon)
    curvature = None
    if len(prior_log_returns) >= 1:
        previous_return = float(prior_log_returns[-1])
        if not math.isfinite(previous_return):
            raise ValueError("prior returns must be finite")
        # Curvature of the sampled log-price path; denominator stabilizes large slopes.
        slope = current_log_return / scale
        previous_slope = previous_return / scale
        second_difference = slope - previous_slope
        curvature = second_difference / ((1.0 + slope * slope) ** 1.5)
    return {
        "log_displacement": displacement,
        "normalized_displacement": normalized_displacement,
        "potential_proxy": potential,
        "kinetic_proxy_normalized": kinetic_proxy,
        "kinetic_potential_ratio": energy_ratio,
        "path_curvature_proxy": curvature,
    }


def first_touch_barrier_label(
    rows: list[tuple[float, float, float]],
    start_index: int,
    upper_barrier: float,
    lower_barrier: float,
    horizon: int,
) -> str:
    """Label future (high, low, close) bars; ties within one OHLC bar are AMBIGUOUS.

    Barriers are absolute price levels and are checked strictly after the signal bar.
    """
    if horizon < 1 or start_index < 0 or start_index >= len(rows):
        raise ValueError("invalid start_index or horizon")
    if not (
        math.isfinite(upper_barrier)
        and math.isfinite(lower_barrier)
        and upper_barrier > lower_barrier
    ):
        raise ValueError("upper barrier must exceed lower barrier and both be finite")
    stop = min(len(rows), start_index + horizon + 1)
    for high, low, _close in rows[start_index + 1 : stop]:
        hit_up = high >= upper_barrier
        hit_down = low <= lower_barrier
        if hit_up and hit_down:
            return "AMBIGUOUS"
        if hit_up:
            return "UP_FIRST"
        if hit_down:
            return "DOWN_FIRST"
    return "TIMEOUT"


__all__ = ["potential_geometry_features", "first_touch_barrier_label"]
