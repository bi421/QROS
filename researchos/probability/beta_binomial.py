"""Deterministic Beta-Binomial probability primitives.

Research-only conjugate Bayesian inference for binary event rates. No fitting,
sampling, or external numerical dependencies are used.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BetaBinomialPosterior:
    """Posterior Beta(alpha, beta) with explicit prior and observation counts."""

    alpha: float
    beta: float
    prior_alpha: float
    prior_beta: float
    successes: int
    failures: int

    def __post_init__(self) -> None:
        for name in ("alpha", "beta", "prior_alpha", "prior_beta"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and > 0")
        if self.successes < 0 or self.failures < 0:
            raise ValueError("successes and failures must be >= 0")
        if not math.isclose(self.alpha, self.prior_alpha + self.successes, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("alpha must equal prior_alpha + successes")
        if not math.isclose(self.beta, self.prior_beta + self.failures, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("beta must equal prior_beta + failures")

    @property
    def sample_size(self) -> int:
        return self.successes + self.failures

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def variance(self) -> float:
        total = self.alpha + self.beta
        return self.alpha * self.beta / (total * total * (total + 1.0))

    def predictive_probability(self, successes: int, trials: int) -> float:
        return beta_binomial_pmf(successes, trials, self.alpha, self.beta)

    def predictive_mean(self, trials: int) -> float:
        if trials < 0:
            raise ValueError("trials must be >= 0")
        return trials * self.mean


def beta_binomial_posterior(
    successes: int,
    failures: int,
    *,
    prior_alpha: float = 1.0,
    prior_beta: float = 1.0,
) -> BetaBinomialPosterior:
    """Construct the conjugate Beta posterior for binary observations."""
    if successes < 0 or failures < 0:
        raise ValueError("successes and failures must be >= 0")
    if not math.isfinite(prior_alpha) or prior_alpha <= 0.0:
        raise ValueError("prior_alpha must be finite and > 0")
    if not math.isfinite(prior_beta) or prior_beta <= 0.0:
        raise ValueError("prior_beta must be finite and > 0")
    return BetaBinomialPosterior(
        alpha=prior_alpha + successes,
        beta=prior_beta + failures,
        prior_alpha=prior_alpha,
        prior_beta=prior_beta,
        successes=successes,
        failures=failures,
    )


def beta_binomial_pmf(successes: int, trials: int, alpha: float, beta: float) -> float:
    """Return the exact Beta-Binomial predictive PMF at one count."""
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("successes must be in [0, trials] and trials must be >= 0")
    if not math.isfinite(alpha) or alpha <= 0.0:
        raise ValueError("alpha must be finite and > 0")
    if not math.isfinite(beta) or beta <= 0.0:
        raise ValueError("beta must be finite and > 0")
    log_p = (
        math.lgamma(trials + 1.0)
        - math.lgamma(successes + 1.0)
        - math.lgamma(trials - successes + 1.0)
        + math.lgamma(successes + alpha)
        + math.lgamma(trials - successes + beta)
        - math.lgamma(trials + alpha + beta)
        + math.lgamma(alpha + beta)
        - math.lgamma(alpha)
        - math.lgamma(beta)
    )
    return min(1.0, max(0.0, math.exp(log_p)))


def beta_binomial_predictive_distribution(
    trials: int, alpha: float, beta: float
) -> tuple[float, ...]:
    """Return the full deterministic predictive PMF for 0..trials successes."""
    if trials < 0:
        raise ValueError("trials must be >= 0")
    probabilities = tuple(beta_binomial_pmf(k, trials, alpha, beta) for k in range(trials + 1))
    if not math.isclose(math.fsum(probabilities), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ArithmeticError("Beta-Binomial PMF failed normalization")
    return probabilities
