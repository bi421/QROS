"""Deterministic probability and trading-edge research primitives."""

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
    "ProbabilityAnalysis",
    "ProbabilityMethod",
    "expected_value",
    "historical_expected_shortfall",
    "historical_var",
    "kelly_fraction",
    "mutual_information",
    "shannon_entropy",
]
