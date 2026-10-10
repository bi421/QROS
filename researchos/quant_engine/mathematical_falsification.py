"""Independent mathematical audits for existing quant-math outputs.

These checks verify arithmetic/model-contract consistency. They do NOT prove
that the assumptions describe markets or that a strategy will be profitable.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


class AuditStatus(str, Enum):
    VERIFIED = "VERIFIED"
    FALSIFIED = "FALSIFIED"
    INCONCLUSIVE = "INCONCLUSIVE"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True)
class MathematicalAudit:
    model: str
    status: AuditStatus
    checked_claim: str
    expected: float | None
    reported: float | None
    absolute_error: float | None
    tolerance: float
    assumptions: tuple[str, ...]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "status": self.status.value,
            "checked_claim": self.checked_claim,
            "expected": self.expected,
            "reported": self.reported,
            "absolute_error": self.absolute_error,
            "tolerance": self.tolerance,
            "assumptions": list(self.assumptions),
            "explanation": self.explanation,
        }


def _number(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def audit_beta_bernoulli(
    measurement: Mapping[str, Any], *, tolerance: float = 1e-12
) -> MathematicalAudit:
    """Independently verify Beta-Bernoulli conjugate-update arithmetic.

    Checks posterior_alpha = prior_alpha + successes,
    posterior_beta = prior_beta + failures, and posterior_mean = a/(a+b).
    This is an arithmetic/model-contract audit, not proof that Bernoulli
    independence or the prior is appropriate for market data.
    """
    try:
        prior_alpha = _number(measurement["prior_alpha"], "prior_alpha")
        prior_beta = _number(measurement["prior_beta"], "prior_beta")
        successes_value = _number(measurement["successes"], "successes")
        failures_value = _number(measurement["failures"], "failures")
        reported_alpha = _number(measurement["posterior_alpha"], "posterior_alpha")
        reported_beta = _number(measurement["posterior_beta"], "posterior_beta")
        reported_mean = _number(measurement["posterior_mean"], "posterior_mean")
        if prior_alpha <= 0 or prior_beta <= 0:
            raise ValueError("Beta prior parameters must be positive")
        if successes_value < 0 or failures_value < 0:
            raise ValueError("successes and failures must be non-negative")
        if not successes_value.is_integer() or not failures_value.is_integer():
            raise ValueError("successes and failures must be integers")
        expected_alpha = prior_alpha + successes_value
        expected_beta = prior_beta + failures_value
        expected_mean = expected_alpha / (expected_alpha + expected_beta)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return MathematicalAudit(
            "beta_bernoulli", AuditStatus.INVALID_INPUT, "posterior update",
            None, None, None, tolerance, (),
            f"Cannot verify the claim: {exc}",
        )

    checks = (
        (reported_alpha, expected_alpha, "posterior_alpha"),
        (reported_beta, expected_beta, "posterior_beta"),
        (reported_mean, expected_mean, "posterior_mean"),
    )
    failures = [
        (name, actual, expected, abs(actual - expected))
        for actual, expected, name in checks
        if abs(actual - expected) > tolerance
    ]
    if failures:
        name, actual, expected, error = max(failures, key=lambda item: item[3])
        return MathematicalAudit(
            "beta_bernoulli", AuditStatus.FALSIFIED, name, expected, actual,
            error, tolerance,
            ("Beta prior is valid", "observations are Bernoulli and conditionally exchangeable"),
            f"Reported {name} violates the conjugate-update identity; maximum failing field: {name}.",
        )
    return MathematicalAudit(
        "beta_bernoulli", AuditStatus.VERIFIED, "posterior_mean",
        expected_mean, reported_mean, abs(expected_mean - reported_mean), tolerance,
        ("Beta prior is valid", "observations are Bernoulli and conditionally exchangeable"),
        "All posterior parameters match the Beta-Bernoulli identities. This verifies arithmetic only; market-model assumptions remain unverified.",
    )


def audit_monte_carlo_summary(
    measurement: Mapping[str, Any], *, tolerance: float = 1e-10
) -> MathematicalAudit:
    """Check internal consistency of a Monte Carlo summary.

    This catches impossible summaries, not faulty paths or misspecified
    stochastic assumptions. Raw paths and a versioned generator are required
    for a stronger independent replay audit.
    """
    try:
        simulations = int(measurement["simulations"])
        mean = _number(measurement["mean_terminal"], "mean_terminal")
        sd = _number(measurement["standard_deviation_terminal"], "standard_deviation_terminal")
        p05 = _number(measurement["percentile_05"], "percentile_05")
        p50 = _number(measurement["percentile_50"], "percentile_50")
        p95 = _number(measurement["percentile_95"], "percentile_95")
        if simulations < 1:
            raise ValueError("simulations must be positive")
        if sd < 0:
            raise ValueError("standard deviation cannot be negative")
        if p05 > p50 or p50 > p95:
            raise ValueError("reported percentiles must satisfy p05 <= p50 <= p95")
        if min(mean, p05, p50, p95) < 0:
            raise ValueError("terminal prices must be non-negative")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return MathematicalAudit(
            "monte_carlo", AuditStatus.INVALID_INPUT, "summary consistency",
            None, None, None, tolerance, (),
            f"Cannot verify the claim: {exc}",
        )

    # A non-negative terminal-price distribution must have its mean within
    # the support interval's broad moment bounds; percentile ordering is the
    # only distribution-free constraint inferable from this summary alone.
    # Mark a coherent summary as inconclusive, not proven correct, because
    # aggregate summaries cannot reconstruct or independently verify paths.
    return MathematicalAudit(
        "monte_carlo", AuditStatus.INCONCLUSIVE, "summary consistency",
        None, mean, None, tolerance,
        ("terminal values are non-negative", "percentiles summarize the same simulation sample"),
        "Basic summary constraints pass, but aggregate fields cannot prove the simulation paths, RNG, sampling assumptions, or reported moments. Raw paths and generator/version metadata are required for independent replay.",
    )


def audit_monte_carlo_replay(
    prices: Sequence[float],
    measurement: Mapping[str, Any],
    *,
    tolerance: float = 1e-10,
) -> MathematicalAudit:
    """Independently replay the current empirical-resampling terminal model.

    The replay reproduces the declared algorithm from raw prices, simulation
    count, and seed without calling the production Monte Carlo function.
    VERIFIED means numerical reproducibility only; it does not validate the
    iid-resampling assumption or establish predictive market validity.
    """
    try:
        values = [_number(value, "price") for value in prices]
        if len(values) < 2 or any(value <= 0 for value in values):
            raise ValueError("at least two finite positive prices are required")
        simulations_value = _number(measurement["simulations"], "simulations")
        seed_value = _number(measurement["seed"], "seed")
        if not simulations_value.is_integer() or simulations_value < 1:
            raise ValueError("simulations must be a positive integer")
        if not seed_value.is_integer():
            raise ValueError("seed must be an integer")
        reported = {
            "mean_terminal": _number(measurement["mean_terminal"], "mean_terminal"),
            "standard_deviation_terminal": _number(
                measurement["standard_deviation_terminal"], "standard_deviation_terminal"
            ),
            "percentile_05": _number(measurement["percentile_05"], "percentile_05"),
            "percentile_50": _number(measurement["percentile_50"], "percentile_50"),
            "percentile_95": _number(measurement["percentile_95"], "percentile_95"),
        }
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return MathematicalAudit(
            "monte_carlo_replay", AuditStatus.INVALID_INPUT, "replay inputs",
            None, None, None, tolerance, (),
            f"Cannot replay the claim: {exc}",
        )

    returns = [
        values[index] / values[index - 1] - 1.0
        for index in range(1, len(values))
    ]
    rng = random.Random(int(seed_value))
    terminals = []
    for _ in range(int(simulations_value)):
        terminal = values[0]
        for _ in returns:
            terminal *= 1.0 + rng.choice(returns)
        terminals.append(terminal)
    terminals.sort()

    def quantile(probability: float) -> float:
        position = probability * (len(terminals) - 1)
        low = math.floor(position)
        high = math.ceil(position)
        if low == high:
            return terminals[low]
        weight = position - low
        return terminals[low] * (1.0 - weight) + terminals[high] * weight

    mean = math.fsum(terminals) / len(terminals)
    sd = math.sqrt(math.fsum((value - mean) ** 2 for value in terminals) / len(terminals))
    expected = {
        "mean_terminal": mean,
        "standard_deviation_terminal": sd,
        "percentile_05": quantile(0.05),
        "percentile_50": quantile(0.50),
        "percentile_95": quantile(0.95),
    }
    errors = {
        name: abs(expected[name] - reported[name])
        for name in expected
    }
    worst_name = max(errors, key=errors.get)
    worst_error = errors[worst_name]
    status = (
        AuditStatus.VERIFIED
        if all(error <= tolerance for error in errors.values())
        else AuditStatus.FALSIFIED
    )
    return MathematicalAudit(
        "monte_carlo_replay",
        status,
        worst_name,
        expected[worst_name],
        reported[worst_name],
        worst_error,
        tolerance,
        (
            "same input prices and simulation horizon",
            "Python random.Random behavior and seed are part of the replay contract",
            "historical returns are resampled independently with replacement",
        ),
        (
            "Reported Monte Carlo summary matches an independent replay numerically. "
            "This does not validate the iid-resampling assumption or future profitability."
            if status is AuditStatus.VERIFIED
            else f"Independent replay disagrees with reported {worst_name}; numerical claim is falsified."
        ),
    )
