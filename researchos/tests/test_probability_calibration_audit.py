"""Tests for the independent probability calibration audit."""

from __future__ import annotations

from copy import deepcopy

from researchos.decision_engine.probability import ProbabilityAssessment
from researchos.probability_validation import evaluate_probability_calibration
from researchos.quant_engine.mathematical_falsification import AuditStatus
from researchos.quant_engine.probability_calibration_audit import audit_probability_calibration


def _assessment(bullish: float, bearish: float, neutral: float) -> ProbabilityAssessment:
    return ProbabilityAssessment(
        decision_context_id="audit-context",
        evidence_collection_id="audit-evidence",
        bullish_probability=bullish,
        bearish_probability=bearish,
        neutral_probability=neutral,
        confidence=max(bullish, bearish, neutral),
        uncertainty=1.0 - max(bullish, bearish, neutral),
        sample_size=10,
    )


def test_independent_calibration_audit_verifies_report() -> None:
    assessments = [
        _assessment(0.9, 0.05, 0.05),
        _assessment(0.2, 0.7, 0.1),
        _assessment(0.3, 0.3, 0.4),
    ]
    outcomes = ["bullish", "bearish", "neutral"]
    report = evaluate_probability_calibration(
        assessments, outcomes, bin_count=5, minimum_calibration_sample=3
    ).to_dict()

    audit = audit_probability_calibration(
        assessments, outcomes, report, bin_count=5, minimum_calibration_sample=3
    )

    assert audit.status is AuditStatus.VERIFIED


def test_independent_calibration_audit_falsifies_tampered_brier_score() -> None:
    assessments = [_assessment(0.8, 0.1, 0.1), _assessment(0.1, 0.8, 0.1)]
    outcomes = ["bullish", "bearish"]
    report = evaluate_probability_calibration(
        assessments, outcomes, minimum_calibration_sample=2
    ).to_dict()
    report["brier_score"] += 0.2

    audit = audit_probability_calibration(
        assessments, outcomes, report, minimum_calibration_sample=2
    )

    assert audit.status is AuditStatus.FALSIFIED
    assert audit.checked_claim == "brier_score"


def test_independent_calibration_audit_preserves_infinite_log_loss() -> None:
    assessments = [_assessment(1.0, 0.0, 0.0)]
    outcomes = ["bearish"]
    report = evaluate_probability_calibration(
        assessments, outcomes, minimum_calibration_sample=1
    ).to_dict()

    audit = audit_probability_calibration(
        assessments, outcomes, report, minimum_calibration_sample=1
    )

    assert report["log_loss"] == float("inf")
    assert audit.status is AuditStatus.VERIFIED


def test_independent_calibration_audit_rejects_wrong_sample_gate() -> None:
    assessments = [_assessment(0.6, 0.3, 0.1)]
    outcomes = ["bullish"]
    report = evaluate_probability_calibration(
        assessments, outcomes, minimum_calibration_sample=30
    ).to_dict()
    report["calibration_status"] = "CALIBRATION_READY"

    audit = audit_probability_calibration(
        assessments, outcomes, report, minimum_calibration_sample=30
    )

    assert audit.status is AuditStatus.INVALID_INPUT
