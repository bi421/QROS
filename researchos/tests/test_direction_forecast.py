"""Tests for the canonical three-way market-direction output."""

import pytest

from researchos.decision_engine.direction import classify_direction
from researchos.decision_engine.probability import ProbabilityAssessment


def assessment(up: float, down: float, neutral: float) -> ProbabilityAssessment:
    return ProbabilityAssessment(
        decision_context_id="xauusd-test",
        evidence_collection_id="evidence-test",
        bullish_probability=up,
        bearish_probability=down,
        neutral_probability=neutral,
        confidence=max(up, down, neutral),
        uncertainty=1.0 - max(up, down, neutral),
        sample_size=12,
    )


@pytest.mark.parametrize(
    ("probabilities", "expected"),
    [
        ((0.70, 0.20, 0.10), "UP"),
        ((0.15, 0.65, 0.20), "DOWN"),
        ((0.20, 0.25, 0.55), "NEUTRAL"),
        ((1 / 3, 1 / 3, 1 / 3), "NEUTRAL"),
        ((0.45, 0.45, 0.10), "NEUTRAL"),
        ((0.40, 0.20, 0.40), "NEUTRAL"),
        ((0.5000000000001, 0.5, 0.0), "NEUTRAL"),
        ((0.5000000001, 0.5, 0.0), "UP"),
        ((0.0, 0.5000000000001, 0.5), "NEUTRAL"),
        ((0.0, 0.5000000001, 0.5), "DOWN"),
    ],
)
def test_direction_is_exactly_one_of_three_classes(probabilities, expected):
    result = classify_direction(assessment(*probabilities))
    assert result.direction == expected
    assert result.direction in {"UP", "DOWN", "NEUTRAL"}
    assert result.confidence == max(probabilities)


def test_forecast_serializes_probabilities_and_provenance():
    result = classify_direction(assessment(0.6, 0.3, 0.1))
    payload = result.to_dict()
    assert payload["direction"] == "UP"
    assert payload["up_probability"] == 0.6
    assert payload["down_probability"] == 0.3
    assert payload["neutral_probability"] == 0.1
    assert payload["calculation_version"] == "PROBABILITY_V1"
    assert payload["assessment_hash"]


@pytest.mark.parametrize(
    "probabilities",
    [
        (float("nan"), 0.2, 0.8),
        (float("inf"), 0.0, 0.0),
        (-0.1, 0.5, 0.6),
        (0.6, 0.3, 0.3),
    ],
)
def test_invalid_distribution_fails_closed(probabilities):
    with pytest.raises(ValueError):
        classify_direction(assessment(*probabilities))
