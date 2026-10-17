"""Fail-closed economic gate for probability-based research signals.

A verified cost audit and ordered net returns are mandatory. The 95% moving-block
bootstrap lower bound must be strictly positive to pass. Research only, no orders.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from researchos.market_memory.bootstrap import block_bootstrap_mean_ci


def evaluate_net_expectancy_gate(
    *,
    win_probability: float,
    average_win: float,
    average_loss: float,
    roundtrip_cost: float | None,
    minimum_net_expectancy: float = 0.0,
    fractional_kelly: float = 0.25,
    max_risk_fraction: float = 0.01,
    costs_verified: bool = False,
    net_returns: Sequence[float] | None = None,
    block_size: int | None = None,
    minimum_block_size: int = 1,
    bootstrap_replicates: int = 999,
    seed: int = 20261017,
    minimum_observations: int = 100,
) -> dict[str, Any]:
    """Gate on point expectancy and the CI of all-in net returns.

    All payoff, cost, and net-return values must use the same units. net_returns
    must be chronologically ordered, include all costs, and come from a predeclared
    evaluation slice not used to fit or tune parameters.
    """
    values = (win_probability, average_win, average_loss, minimum_net_expectancy)
    if not all(math.isfinite(float(v)) for v in values):
        raise ValueError("probability, payoff estimates and threshold must be finite")
    if not 0.0 <= win_probability <= 1.0:
        raise ValueError("win_probability must be within [0, 1]")
    if average_win < 0 or average_loss < 0 or minimum_net_expectancy < 0:
        raise ValueError("payoff magnitudes and minimum expectancy must be >= 0")
    if not math.isfinite(float(fractional_kelly)) or not 0.0 < fractional_kelly <= 1.0:
        raise ValueError("fractional_kelly must be finite and in (0, 1]")
    if not math.isfinite(float(max_risk_fraction)) or not 0.0 <= max_risk_fraction <= 1.0:
        raise ValueError("max_risk_fraction must be finite and in [0, 1]")
    if roundtrip_cost is None:
        return {
            "status": "NO_TRADE_COSTS_UNKNOWN",
            "signal_allowed": False,
            "net_expectancy": None,
            "ci_95_percent": None,
            "reason": "verified all-in round-trip cost is missing",
        }
    if not math.isfinite(float(roundtrip_cost)) or roundtrip_cost < 0:
        raise ValueError("roundtrip_cost must be finite and >= 0")
    if not costs_verified:
        return {
            "status": "NO_TRADE_COST_AUDIT_UNVERIFIED",
            "signal_allowed": False,
            "net_expectancy": None,
            "ci_95_percent": None,
            "reason": "spread, commission and slippage audit is not verified",
        }
    if net_returns is None:
        return {
            "status": "NO_TRADE_NET_RETURNS_MISSING",
            "signal_allowed": False,
            "net_expectancy": None,
            "ci_95_percent": None,
            "reason": "ordered per-trade net returns after all costs are required",
        }
    returns = [float(value) for value in net_returns]
    if any(not math.isfinite(value) for value in returns):
        raise ValueError("net_returns must contain only finite values")
    if (
        isinstance(minimum_observations, bool)
        or not isinstance(minimum_observations, int)
        or minimum_observations < 2
    ):
        raise ValueError("minimum_observations must be an integer >= 2")
    if len(returns) < minimum_observations:
        return {
            "status": "NO_TRADE_INSUFFICIENT_NET_RETURNS",
            "signal_allowed": False,
            "net_expectancy": None,
            "ci_95_percent": None,
            "observation_count": len(returns),
            "reason": "too few ordered net-return observations for the configured gate",
        }
    if (
        isinstance(bootstrap_replicates, bool)
        or not isinstance(bootstrap_replicates, int)
        or bootstrap_replicates < 199
    ):
        raise ValueError("bootstrap_replicates must be an integer >= 199")
    if (
        isinstance(minimum_block_size, bool)
        or not isinstance(minimum_block_size, int)
        or minimum_block_size < 1
    ):
        raise ValueError("minimum_block_size must be an integer >= 1")
    chosen_block_size = (
        block_size
        if block_size is not None
        else max(minimum_block_size, 2, round(len(returns) ** (1 / 3)))
    )
    if isinstance(chosen_block_size, bool) or not isinstance(chosen_block_size, int):
        raise ValueError("block_size must be an integer")
    if not minimum_block_size <= chosen_block_size <= len(returns):
        raise ValueError("block_size must be between minimum_block_size and observation count")

    gross = win_probability * average_win - (1.0 - win_probability) * average_loss
    net = gross - roundtrip_cost
    ci = block_bootstrap_mean_ci(
        returns,
        block_size=chosen_block_size,
        num_resamples=bootstrap_replicates,
        seed=seed,
        confidence_level=0.95,
    ).confidence_interval
    ci_lower, ci_upper = float(ci[0]), float(ci[1])
    allowed = net > minimum_net_expectancy and ci_lower > 0.0
    # Kelly uses cost-adjusted win/loss magnitudes and remains zero unless the
    # independent net-return CI has passed. This is a sizing diagnostic only.
    net_average_win = average_win - roundtrip_cost
    net_average_loss = average_loss + roundtrip_cost
    full_kelly = 0.0
    if allowed and net_average_win > 0.0 and net_average_loss > 0.0:
        payoff_ratio = net_average_win / net_average_loss
        full_kelly = max(0.0, win_probability - (1.0 - win_probability) / payoff_ratio)
    quarter_kelly = full_kelly * fractional_kelly
    capped_risk_fraction = min(quarter_kelly, max_risk_fraction) if allowed else 0.0
    if allowed and net_average_win <= 0.0:
        allowed = False
        full_kelly = quarter_kelly = capped_risk_fraction = 0.0
    return {
        "status": "PASS_NET_EXPECTANCY_AND_CI" if allowed else "NO_TRADE_NET_EXPECTANCY_OR_CI",
        "signal_allowed": allowed,
        "gross_expectancy": gross,
        "roundtrip_cost": roundtrip_cost,
        "net_expectancy": net,
        "minimum_net_expectancy": minimum_net_expectancy,
        "net_average_win_after_cost": net_average_win,
        "net_average_loss_after_cost": net_average_loss,
        "full_kelly_fraction_after_cost": full_kelly,
        "fractional_kelly_multiplier": fractional_kelly,
        "fractional_kelly_fraction_after_cost": quarter_kelly,
        "max_risk_fraction_cap": max_risk_fraction,
        "recommended_risk_fraction": capped_risk_fraction,
        "ci_95_percent": [ci_lower, ci_upper],
        "ci_method": "moving_block_bootstrap",
        "block_size": chosen_block_size,
        "minimum_block_size": minimum_block_size,
        "bootstrap_replicates": bootstrap_replicates,
        "observation_count": len(returns),
        "costs_verified": costs_verified,
        "reason": "point expectancy and 95% CI lower bound clear thresholds"
        if allowed
        else "point expectancy threshold or strictly-positive 95% CI lower bound failed",
    }


__all__ = ["evaluate_net_expectancy_gate"]
