"""Deterministic probability and trading-edge research primitives."""

from researchos.probability.conditional import (
    bayes_probability,
    bayes_probability_from_counts,
    conditional_probability,
    conditional_probability_from_counts,
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
    "CalibrationResult",
    "EconomicCostContext",
    "ProbabilityAnalysis",
    "ProbabilityMethod",
    "bayes_probability",
    "bayes_probability_from_counts",
    "conditional_probability",
    "conditional_probability_from_counts",
    "brier_score",
    "expected_value",
    "historical_expected_shortfall",
    "historical_var",
    "kelly_fraction",
    "mutual_information",
    "shannon_entropy",
    "wilson_interval",
]
