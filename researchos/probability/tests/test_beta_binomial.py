"""Tests for canonical Beta-Binomial probability primitives."""
import math

import pytest

from researchos.probability.beta_binomial import (
    beta_binomial_pmf,
    beta_binomial_posterior,
    beta_binomial_predictive_distribution,
)


def test_posterior_is_conjugate_and_deterministic() -> None:
    posterior = beta_binomial_posterior(7, 3)
    assert posterior.alpha == 8.0
    assert posterior.beta == 4.0
    assert posterior.sample_size == 10
    assert posterior.mean == pytest.approx(2.0 / 3.0)


def test_uniform_prior_predictive_is_uniform() -> None:
    probabilities = beta_binomial_predictive_distribution(4, 1.0, 1.0)
    assert probabilities == pytest.approx((0.2,) * 5)
    assert math.fsum(probabilities) == pytest.approx(1.0)


def test_predictive_pmf_is_normalized() -> None:
    probabilities = beta_binomial_predictive_distribution(12, 3.0, 5.0)
    assert math.fsum(probabilities) == pytest.approx(1.0)
    assert all(0.0 <= value <= 1.0 for value in probabilities)


def test_predictive_mean_uses_posterior_mean() -> None:
    posterior = beta_binomial_posterior(7, 3)
    assert posterior.predictive_mean(9) == pytest.approx(6.0)


@pytest.mark.parametrize("successes, failures", [(-1, 2), (2, -1)])
def test_negative_counts_rejected(successes: int, failures: int) -> None:
    with pytest.raises(ValueError):
        beta_binomial_posterior(successes, failures)


def test_invalid_pmf_count_rejected() -> None:
    with pytest.raises(ValueError):
        beta_binomial_pmf(5, 4, 1.0, 1.0)
