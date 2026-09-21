"""Deterministic probability and trading-edge research primitives."""

from researchos.probability.beta_binomial import (
    BetaBinomialPosterior,
    beta_binomial_pmf,
    beta_binomial_posterior,
    beta_binomial_predictive_distribution,
)
from researchos.probability.calibration import CalibrationResult, brier_score, wilson_interval
from researchos.probability.economic_cost import EconomicCostContext
from researchos.probability.contracts import ProbabilityAnalysis, ProbabilityMethod
from researchos.probability.primitives import (
    expected_value,
    historical_expected_shortfall,
    historical_var,
    kelly_fraction,
    mutual_information,
    shannon_entropy,
)

__all__ = [
    "BetaBinomialPosterior",
    "CalibrationResult",
    "EconomicCostContext",
    "ProbabilityAnalysis",
    "ProbabilityMethod",
    "beta_binomial_pmf",
    "beta_binomial_posterior",
    "beta_binomial_predictive_distribution",
    "brier_score",
    "expected_value",
    "historical_expected_shortfall",
    "historical_var",
    "kelly_fraction",
    "mutual_information",
    "shannon_entropy",
    "wilson_interval",
]
