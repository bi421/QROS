"""
Conditional Analysis — deterministic conditional probability and statistics.

Given a set of market events, computes:
  - P(outcome | condition)
  - Conditional mean, std, confidence intervals
  - Multiple-testing audit trail

All analyses are deterministic and record the exact conditions tested.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from researchos.market_memory.bootstrap import block_bootstrap_mean_ci
from researchos.market_memory.event_schema import (
    ConditionalResult,
    ConditionSpec,
    EvidenceStatus,
    MarketEvent,
)


# =============================================================================
# Condition Evaluation
# =============================================================================


def evaluate_condition(event: MarketEvent, spec: ConditionSpec) -> bool:
    """Evaluate whether a single event matches every condition in ``spec``."""
    if event.outcome is None:
        return False

    ctx = event.context
    for key, value in spec.conditions.items():
        if key == "direction":
            if event.direction != value:
                return False
        elif key == "market_regime":
            if ctx.market_regime != value:
                return False
        elif key == "volatility_state":
            if ctx.volatility_state != value:
                return False
        elif key == "session":
            if ctx.session != value:
                return False
        elif key == "day_of_week":
            if ctx.day_of_week != value:
                return False
        elif key == "sma_fast_above_slow":
            if bool(ctx.sma_fast > ctx.sma_slow) != value:
                return False
        elif key == "atr_percentile":
            # Not implemented in V1: fail closed rather than silently ignoring it.
            return False
        else:
            # Unknown condition key: fail closed to prevent accidental broad matches.
            return False
    return True


def filter_events(events: list[MarketEvent], spec: ConditionSpec) -> list[MarketEvent]:
    """Filter events that match a condition specification."""
    return [event for event in events if evaluate_condition(event, spec)]


# =============================================================================
# Conditional Statistics
# =============================================================================


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / len(values))


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def compute_conditional_statistics(
    events: list[MarketEvent],
    spec: ConditionSpec,
    outcome_field: str = "return_1d",
    bootstrap_num_resamples: int = 1000,
    bootstrap_seed: int = 42,
    confidence_level: float = 0.95,
    dependence_block_size: int = 1,
) -> ConditionalResult:
    """Compute deterministic conditional statistics for matching events.

    Invalid statistical parameters are rejected explicitly. Non-finite outcome
    values are excluded from the empirical sample rather than contaminating the
    result. No missing-value repair or interpolation is performed.
    """
    if bootstrap_num_resamples < 1:
        raise ValueError("bootstrap_num_resamples must be >= 1")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be strictly between 0 and 1")
    if not isinstance(bootstrap_seed, int):
        raise TypeError("bootstrap_seed must be an int")
    if not outcome_field or not isinstance(outcome_field, str):
        raise ValueError("outcome_field must be a non-empty string")

    matched = filter_events(events, spec)

    values: list[float] = []
    for event in matched:
        value = getattr(event.outcome, outcome_field, None) if event.outcome else None
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            values.append(float(value))

    n = len(values)
    if n == 0:
        return ConditionalResult(
            condition_name=spec.name,
            condition_spec=spec,
            sample_size=0,
            raw_probability=0.0,
            mean_return=0.0,
            std_return=0.0,
            status=EvidenceStatus.INCONCLUSIVE.value,
            notes="No finite outcomes matched condition",
        )

    mean_val = _mean(values)
    std_val = _std(values)
    positive_count = sum(1 for value in values if value > 0)
    raw_prob = positive_count / n
    effective_block_size = min(dependence_block_size, n)
    ci_result = block_bootstrap_mean_ci(
        values, effective_block_size, bootstrap_num_resamples, bootstrap_seed, confidence_level
    )
    ci = ci_result.confidence_interval if len(values) >= 2 else None

    if n < 5:
        status = EvidenceStatus.EXPLORATORY.value
        dependence_note = (
            f"; dependence_block_size={effective_block_size}"
            if effective_block_size > 1
            else "; iid_bootstrap_only_when_no_overlap"
        )
        notes = (
            f"Small sample (n={n}); "
            f"uncertainty_method={ci_result.method if n >= 2 else 'none'}"
            f"{dependence_note}"
        )
    else:
        status = EvidenceStatus.UNVALIDATED.value
        dependence_note = (
            f"; dependence_block_size={effective_block_size}"
            if effective_block_size > 1
            else "; iid_bootstrap_only_when_no_overlap"
        )
        notes = f"Sample n={n}, awaiting temporal validation; uncertainty_method={ci_result.method}{dependence_note}"

    return ConditionalResult(
        condition_name=spec.name,
        condition_spec=spec,
        sample_size=n,
        raw_probability=raw_prob,
        mean_return=mean_val,
        std_return=std_val,
        confidence_interval=ci,
        bootstrap_seed=bootstrap_seed,
        bootstrap_num_resamples=bootstrap_num_resamples,
        status=status,
        notes=notes,
    )


def _bootstrap_mean_ci(
    values: list[float],
    num_resamples: int,
    seed: int,
    confidence_level: float,
) -> tuple[float, float] | None:
    """Compute a deterministic percentile-bootstrap confidence interval."""
    if len(values) < 2:
        return None
    if num_resamples < 1:
        raise ValueError("num_resamples must be >= 1")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be strictly between 0 and 1")

    import random

    rng = random.Random(seed)
    n = len(values)
    resample_means = [_mean([rng.choice(values) for _ in range(n)]) for _ in range(num_resamples)]
    alpha = 1.0 - confidence_level
    return (
        _percentile(resample_means, alpha / 2.0),
        _percentile(resample_means, 1.0 - alpha / 2.0),
    )


# =============================================================================
# Multiple Testing Audit
# =============================================================================


@dataclass
class MultipleTestingAudit:
    """Audit trail for multiple hypothesis testing."""

    total_hypotheses_tested: int = 0
    conditions_tested: list[str] | None = None
    selection_process: str = ""
    correction_applied: str = "None"
    limitations: str = ""

    def __post_init__(self) -> None:
        if self.conditions_tested is None:
            self.conditions_tested = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_hypotheses_tested": self.total_hypotheses_tested,
            "conditions_tested": self.conditions_tested,
            "selection_process": self.selection_process,
            "correction_applied": self.correction_applied,
            "limitations": self.limitations,
        }
