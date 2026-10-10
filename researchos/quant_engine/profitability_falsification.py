"""Conservative, falsification-first gate for net trading evidence.

Inputs are aligned per-period simple returns. The caller must provide returns
after all declared execution costs; this module never estimates missing costs.
A PASS is limited to the supplied sample and bootstrap assumptions.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class ProfitabilityVerdict(str, Enum):
    SUPPORTED_IN_SAMPLE = "SUPPORTED_IN_SAMPLE"
    NOT_PROFITABLE = "NOT_PROFITABLE"
    NO_BENCHMARK_EDGE = "NO_BENCHMARK_EDGE"
    RISK_LIMIT_BREACH = "RISK_LIMIT_BREACH"
    INCONCLUSIVE = "INCONCLUSIVE"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"


@dataclass(frozen=True)
class Interval:
    lower: float
    upper: float


@dataclass(frozen=True)
class ProfitabilityAssessment:
    verdict: ProfitabilityVerdict
    observations: int
    mean_net_return: float | None
    net_return_ci: Interval | None
    mean_excess_return: float | None
    excess_return_ci: Interval | None
    max_drawdown: float | None
    costs_included: bool
    block_length: int
    confidence_level: float
    reasons: tuple[str, ...]

    @property
    def supports_profitability_claim(self) -> bool:
        return self.verdict is ProfitabilityVerdict.SUPPORTED_IN_SAMPLE


def _finite_series(values: Sequence[float], name: str) -> list[float]:
    result = [float(value) for value in values]
    if not result:
        raise ValueError(f"{name} must not be empty")
    if not all(math.isfinite(value) for value in result):
        raise ValueError(f"{name} must contain only finite values")
    if any(value < -1.0 for value in result):
        raise ValueError(f"{name} simple returns cannot be below -1")
    return result


def _quantile(sorted_values: list[float], probability: float) -> float:
    """Linear-interpolated quantile of an already sorted sequence."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    weight = position - lower_index
    return (
        sorted_values[lower_index] * (1.0 - weight)
        + sorted_values[upper_index] * weight
    )


def _moving_block_bootstrap_means(
    values: list[float],
    *,
    block_length: int,
    replicates: int,
    seed: int,
) -> list[float]:
    """Circular moving-block bootstrap preserving short-range dependence."""
    rng = random.Random(seed)
    n = len(values)
    output: list[float] = []
    blocks_per_sample = math.ceil(n / block_length)
    for _ in range(replicates):
        sample: list[float] = []
        for _ in range(blocks_per_sample):
            start = rng.randrange(n)
            for offset in range(block_length):
                sample.append(values[(start + offset) % n])
                if len(sample) == n:
                    break
            if len(sample) == n:
                break
        output.append(math.fsum(sample) / n)
    return output


def _drawdown(returns: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    maximum = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        if peak > 0:
            maximum = max(maximum, (peak - equity) / peak)
    return maximum


def assess_profitability(
    net_returns: Sequence[float],
    benchmark_returns: Sequence[float],
    *,
    costs_included: bool,
    minimum_observations: int = 100,
    confidence_level: float = 0.95,
    block_length: int = 10,
    bootstrap_replicates: int = 4000,
    seed: int = 20261010,
    maximum_drawdown: float = 0.25,
) -> ProfitabilityAssessment:
    """Evaluate profitability and attempt to falsify it using aligned OOS returns.

    Returns are simple returns in decimal units (e.g. 0.01 = +1%). The
    benchmark must use the same timestamps and evaluation periods. Missing or
    undeclared costs, insufficient samples, and malformed inputs fail closed.
    """
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be strictly between 0 and 1")
    if minimum_observations < 2:
        raise ValueError("minimum_observations must be >= 2")
    if block_length < 1:
        raise ValueError("block_length must be >= 1")
    if bootstrap_replicates < 100:
        raise ValueError("bootstrap_replicates must be >= 100")
    if not 0.0 <= maximum_drawdown < 1.0:
        raise ValueError("maximum_drawdown must be in [0, 1)")

    try:
        net = _finite_series(net_returns, "net_returns")
        benchmark = _finite_series(benchmark_returns, "benchmark_returns")
    except (TypeError, ValueError, OverflowError) as exc:
        return ProfitabilityAssessment(
            verdict=ProfitabilityVerdict.INVALID_EVIDENCE,
            observations=0,
            mean_net_return=None,
            net_return_ci=None,
            mean_excess_return=None,
            excess_return_ci=None,
            max_drawdown=None,
            costs_included=costs_included,
            block_length=block_length,
            confidence_level=confidence_level,
            reasons=(str(exc),),
        )

    n = len(net)
    if len(benchmark) != n:
        return ProfitabilityAssessment(
            verdict=ProfitabilityVerdict.INVALID_EVIDENCE,
            observations=n,
            mean_net_return=None,
            net_return_ci=None,
            mean_excess_return=None,
            excess_return_ci=None,
            max_drawdown=None,
            costs_included=costs_included,
            block_length=block_length,
            confidence_level=confidence_level,
            reasons=("net and benchmark returns must be timestamp-aligned and equal length",),
        )

    if not costs_included:
        return ProfitabilityAssessment(
            verdict=ProfitabilityVerdict.INVALID_EVIDENCE,
            observations=n,
            mean_net_return=None,
            net_return_ci=None,
            mean_excess_return=None,
            excess_return_ci=None,
            max_drawdown=None,
            costs_included=False,
            block_length=block_length,
            confidence_level=confidence_level,
            reasons=("transaction costs, spread, and slippage are not declared included",),
        )

    if n < minimum_observations:
        return ProfitabilityAssessment(
            verdict=ProfitabilityVerdict.INCONCLUSIVE,
            observations=n,
            mean_net_return=math.fsum(net) / n,
            net_return_ci=None,
            mean_excess_return=math.fsum(a - b for a, b in zip(net, benchmark)) / n,
            excess_return_ci=None,
            max_drawdown=_drawdown(net),
            costs_included=True,
            block_length=block_length,
            confidence_level=confidence_level,
            reasons=(f"insufficient observations: {n} < {minimum_observations}",),
        )

    effective_block = min(block_length, n)
    excess = [a - b for a, b in zip(net, benchmark)]
    alpha = (1.0 - confidence_level) / 2.0
    net_boot = sorted(
        _moving_block_bootstrap_means(
            net, block_length=effective_block,
            replicates=bootstrap_replicates, seed=seed,
        )
    )
    excess_boot = sorted(
        _moving_block_bootstrap_means(
            excess, block_length=effective_block,
            replicates=bootstrap_replicates, seed=seed + 1,
        )
    )
    net_ci = Interval(_quantile(net_boot, alpha), _quantile(net_boot, 1.0 - alpha))
    excess_ci = Interval(
        _quantile(excess_boot, alpha), _quantile(excess_boot, 1.0 - alpha)
    )
    mean_net = math.fsum(net) / n
    mean_excess = math.fsum(excess) / n
    drawdown = _drawdown(net)
    reasons: list[str] = []

    if drawdown > maximum_drawdown:
        verdict = ProfitabilityVerdict.RISK_LIMIT_BREACH
        reasons.append(
            f"observed maximum drawdown {drawdown:.6f} exceeds limit {maximum_drawdown:.6f}"
        )
    elif net_ci.upper <= 0.0:
        verdict = ProfitabilityVerdict.NOT_PROFITABLE
        reasons.append("upper confidence bound for net mean return is not positive")
    elif excess_ci.upper <= 0.0:
        verdict = ProfitabilityVerdict.NO_BENCHMARK_EDGE
        reasons.append("upper confidence bound for benchmark-relative mean return is not positive")
    elif net_ci.lower > 0.0 and excess_ci.lower > 0.0:
        verdict = ProfitabilityVerdict.SUPPORTED_IN_SAMPLE
        reasons.append(
            "both lower confidence bounds are positive after declared costs; "
            "evidence remains limited to this sample and bootstrap assumptions"
        )
    else:
        verdict = ProfitabilityVerdict.INCONCLUSIVE
        reasons.append(
            "one or more confidence intervals include zero; neither profitability "
            "nor absence of edge is established"
        )

    return ProfitabilityAssessment(
        verdict=verdict,
        observations=n,
        mean_net_return=mean_net,
        net_return_ci=net_ci,
        mean_excess_return=mean_excess,
        excess_return_ci=excess_ci,
        max_drawdown=drawdown,
        costs_included=True,
        block_length=effective_block,
        confidence_level=confidence_level,
        reasons=tuple(reasons),
    )
