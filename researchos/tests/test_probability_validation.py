"""Tests for the Phase 5 probability validation boundary."""

from __future__ import annotations

from math import log

import pytest

from researchos.decision_engine.probability import ProbabilityAssessment
from researchos.probability_validation import (
    PROBABILITY_VALIDATION_SCHEMA_VERSION,
    evaluate_probability_calibration,
    validate_probability_assessment,
)


def _assessment(bullish: float, bearish: float, neutral: float) -> ProbabilityAssessment:
    return ProbabilityAssessment(
        decision_context_id="ctx-1",
        evidence_collection_id="evidence-1",
        bullish_probability=bullish,
        bearish_probability=bearish,
        neutral_probability=neutral,
        confidence=max(bullish, bearish, neutral),
        uncertainty=1.0 - max(bullish, bearish, neutral),
        evidence_strength=0.8,
        historical_consistency=max(bullish, bearish, neutral),
        sample_size=10,
    )


def test_valid_assessment_has_no_validation_errors() -> None:
    assessment = _assessment(0.7, 0.2, 0.1)
    assert validate_probability_assessment(assessment) == ()


def test_calibration_metrics_are_deterministic() -> None:
    assessments = [_assessment(0.9, 0.05, 0.05), _assessment(0.2, 0.7, 0.1)]
    outcomes = ["bullish", "bearish"]

    first = evaluate_probability_calibration(assessments, outcomes, minimum_calibration_sample=2)
    second = evaluate_probability_calibration(assessments, outcomes, minimum_calibration_sample=2)

    assert first.to_dict() == second.to_dict()
    assert first.schema_version == PROBABILITY_VALIDATION_SCHEMA_VERSION
    assert first.brier_score == pytest.approx(0.0775)
    assert first.log_loss == pytest.approx((-log(0.9) - log(0.7)) / 2)
    assert first.expected_calibration_error == pytest.approx(0.1)
    assert first.maximum_calibration_error == pytest.approx(0.1)
    assert first.calibration_status == "CALIBRATION_READY"


def test_insufficient_sample_is_explicitly_not_calibrated() -> None:
    assessment = _assessment(0.6, 0.3, 0.1)
    report = evaluate_probability_calibration(
        [assessment, assessment],
        ["bullish", "bearish"],
        minimum_calibration_sample=30,
    )
    assert report.calibration_status == "INSUFFICIENT_SAMPLE"
    assert report.is_calibration_ready is False
    assert "below minimum 30" in report.limitations[0]


def test_mismatched_pairs_are_rejected() -> None:
    assessment = _assessment(0.6, 0.3, 0.1)
    with pytest.raises(ValueError, match="equal length"):
        evaluate_probability_calibration([assessment], [])


def test_invalid_observed_outcome_is_rejected() -> None:
    assessment = _assessment(0.6, 0.3, 0.1)
    with pytest.raises(ValueError, match="unsupported observed outcome"):
        evaluate_probability_calibration([assessment], ["unknown"])


def test_zero_probability_actual_outcome_has_infinite_log_loss() -> None:
    assessment = _assessment(1.0, 0.0, 0.0)
    report = evaluate_probability_calibration(
        [assessment], ["bearish"], minimum_calibration_sample=1
    )
    assert report.log_loss == float("inf")


def test_invalid_bin_count_is_rejected() -> None:
    assessment = _assessment(0.6, 0.3, 0.1)
    with pytest.raises(ValueError, match="bin_count"):
        evaluate_probability_calibration([assessment], ["bullish"], bin_count=0)
