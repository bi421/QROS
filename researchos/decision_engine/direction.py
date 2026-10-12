"""Canonical three-way market-direction output for QROS.

This layer converts the existing ProbabilityAssessment into exactly one of
UP, DOWN, or NEUTRAL. It does not create or fabricate probabilities; those
remain owned by ProbabilityCalculator and its evidence inputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from researchos.decision_engine.probability import ProbabilityAssessment

MarketDirection = Literal["UP", "DOWN", "NEUTRAL"]
_PROBABILITY_TOLERANCE = 1e-9
_DIRECTION_TIE_REL_TOLERANCE = 1e-12
_DIRECTION_TIE_ABS_TOLERANCE = 1e-15


@dataclass(frozen=True)
class DirectionForecast:
    """Single three-way direction result with its supporting distribution."""

    direction: MarketDirection
    up_probability: float
    down_probability: float
    neutral_probability: float
    confidence: float
    calculation_version: str
    assessment_hash: str

    def to_dict(self) -> dict[str, str | float]:
        """Serialize a stable, UI/API-friendly direction response."""
        return {
            "direction": self.direction,
            "up_probability": self.up_probability,
            "down_probability": self.down_probability,
            "neutral_probability": self.neutral_probability,
            "confidence": self.confidence,
            "calculation_version": self.calculation_version,
            "assessment_hash": self.assessment_hash,
        }


def classify_direction(assessment: ProbabilityAssessment) -> DirectionForecast:
    """Return exactly UP, DOWN, or NEUTRAL from a validated 3-way assessment.

    Probabilities tied within the declared floating-point tolerance resolve to
    NEUTRAL. Invalid or incomplete distributions fail closed instead of
    silently inventing a direction. This is a deterministic classification
    rule, not a claim that the supplied probabilities are empirically calibrated.
    """
    probabilities = (
        float(assessment.bullish_probability),
        float(assessment.bearish_probability),
        float(assessment.neutral_probability),
    )
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in probabilities):
        raise ValueError("direction probabilities must be finite values in [0, 1]")
    if abs(sum(probabilities) - 1.0) > _PROBABILITY_TOLERANCE:
        raise ValueError("direction probabilities must sum to 1.0")

    up, down, neutral = probabilities
    highest = max(probabilities)
    winners = [
        index
        for index, value in enumerate(probabilities)
        if math.isclose(
            value,
            highest,
            rel_tol=_DIRECTION_TIE_REL_TOLERANCE,
            abs_tol=_DIRECTION_TIE_ABS_TOLERANCE,
        )
    ]
    if len(winners) != 1:
        direction: MarketDirection = "NEUTRAL"
    elif winners[0] == 0:
        direction = "UP"
    elif winners[0] == 1:
        direction = "DOWN"
    else:
        direction = "NEUTRAL"

    return DirectionForecast(
        direction=direction,
        up_probability=up,
        down_probability=down,
        neutral_probability=neutral,
        confidence=highest,
        calculation_version=assessment.calculation_version,
        assessment_hash=assessment.assessment_hash,
    )


__all__ = ["DirectionForecast", "MarketDirection", "classify_direction"]
