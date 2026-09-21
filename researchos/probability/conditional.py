"""Deterministic conditional and Bayes probability primitives.

Research-only probability identities with explicit finite-count validation.
"""

from __future__ import annotations

import math


def conditional_probability(joint_probability: float, condition_probability: float) -> float:
    """Return P(A|B) = P(A∩B) / P(B)."""
    _validate_probability(joint_probability, "joint_probability")
    _validate_probability(condition_probability, "condition_probability")
    if joint_probability > condition_probability + 1e-12:
        raise ValueError("joint_probability cannot exceed condition_probability")
    if condition_probability == 0.0:
        raise ValueError("condition_probability must be > 0")
    return joint_probability / condition_probability


def bayes_probability(
    likelihood: float,
    prior: float,
    evidence: float,
) -> float:
    """Return P(H|E) = P(E|H)P(H) / P(E)."""
    for value, name in (
        (likelihood, "likelihood"),
        (prior, "prior"),
        (evidence, "evidence"),
    ):
        _validate_probability(value, name)
    if evidence == 0.0:
        raise ValueError("evidence must be > 0")
    numerator = likelihood * prior
    if numerator > evidence + 1e-12:
        raise ValueError("likelihood * prior cannot exceed evidence")
    return numerator / evidence


def conditional_probability_from_counts(
    joint_count: int,
    condition_count: int,
) -> float:
    """Estimate P(A|B) from exact event counts."""
    if joint_count < 0 or condition_count < 0:
        raise ValueError("counts must be >= 0")
    if joint_count > condition_count:
        raise ValueError("joint_count cannot exceed condition_count")
    if condition_count == 0:
        raise ValueError("condition_count must be > 0")
    return joint_count / condition_count


def bayes_probability_from_counts(
    likelihood_successes: int,
    likelihood_trials: int,
    prior_successes: int,
    prior_trials: int,
    evidence_count: int,
    evidence_trials: int,
) -> float:
    """Compute Bayes posterior from explicit binomial-frequency inputs.

    This helper intentionally requires the caller to provide the evidence
    probability rather than silently constructing incompatible populations.
    """
    if likelihood_trials < 1 or prior_trials < 1 or evidence_trials < 1:
        raise ValueError("trial counts must be >= 1")
    if not 0 <= likelihood_successes <= likelihood_trials:
        raise ValueError("likelihood successes must be in [0, trials]")
    if not 0 <= prior_successes <= prior_trials:
        raise ValueError("prior successes must be in [0, trials]")
    if not 0 <= evidence_count <= evidence_trials:
        raise ValueError("evidence count must be in [0, trials]")
    return bayes_probability(
        likelihood_successes / likelihood_trials,
        prior_successes / prior_trials,
        evidence_count / evidence_trials,
    )


def _validate_probability(value: float, name: str) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1]")
