"""Independent audit of probability calibration reports against raw outcomes.

This verifies reported scoring metrics and reliability bins independently; it
does not prove that observations are independent, representative, or leak-free.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from researchos.decision_engine.probability import ProbabilityAssessment
from researchos.quant_engine.mathematical_falsification import (
    AuditStatus,
    MathematicalAudit,
    _number,
)

_OUTCOMES = ("bullish", "bearish", "neutral")


def audit_probability_calibration(
    assessments: Sequence[ProbabilityAssessment],
    observed_outcomes: Sequence[str],
    report: Mapping[str, Any],
    *,
    bin_count: int = 10,
    minimum_calibration_sample: int = 30,
    tolerance: float = 1e-9,
) -> MathematicalAudit:
    """Recompute calibration scores and reliability bins without production helpers."""
    try:
        if bin_count < 1 or minimum_calibration_sample < 1:
            raise ValueError("bin_count and minimum_calibration_sample must be positive")
        if len(assessments) != len(observed_outcomes):
            raise ValueError("assessment/outcome lengths differ")
        if report["schema_version"] != "probability-validation.v1":
            raise ValueError("unsupported report schema_version")
        n = len(assessments)
        if int(report["assessment_count"]) != n or int(report["outcome_count"]) != n:
            raise ValueError("reported counts do not match raw assessment/outcome pairs")

        scores: list[float] = []
        losses: list[float] = []
        confidence_correct: list[tuple[float, bool]] = []
        for index, (assessment, observed) in enumerate(zip(assessments, observed_outcomes)):
            probs = (
                _number(assessment.bullish_probability, f"assessment[{index}].bullish"),
                _number(assessment.bearish_probability, f"assessment[{index}].bearish"),
                _number(assessment.neutral_probability, f"assessment[{index}].neutral"),
            )
            if any(p < 0.0 or p > 1.0 for p in probs) or abs(math.fsum(probs) - 1.0) > 1e-9:
                raise ValueError(f"assessment {index} has an invalid probability distribution")
            outcome = str(observed).strip().lower()
            if outcome not in _OUTCOMES:
                raise ValueError(f"unsupported observed outcome at index {index}")
            target = _OUTCOMES.index(outcome)
            scores.append(math.fsum((p - (1.0 if i == target else 0.0)) ** 2 for i, p in enumerate(probs)))
            losses.append(math.inf if probs[target] == 0.0 else -math.log(probs[target]))
            predicted = max(range(3), key=lambda i: probs[i])
            confidence_correct.append((probs[predicted], predicted == target))

        expected_brier = math.fsum(scores) / n if n else 0.0
        expected_loss = math.fsum(losses) / n if n else 0.0
        buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bin_count)]
        for confidence, correct in confidence_correct:
            buckets[min(int(confidence * bin_count), bin_count - 1)].append((confidence, correct))
        expected_bins: list[dict[str, float | int]] = []
        for i, bucket in enumerate(buckets):
            if not bucket:
                continue
            mean_confidence = math.fsum(c for c, _ in bucket) / len(bucket)
            accuracy = sum(1 for _, correct in bucket if correct) / len(bucket)
            expected_bins.append({
                "lower_bound": i / bin_count,
                "upper_bound": (i + 1) / bin_count,
                "count": len(bucket),
                "mean_predicted_probability": mean_confidence,
                "observed_frequency": accuracy,
                "absolute_gap": abs(mean_confidence - accuracy),
            })
        expected_ece = math.fsum((b["count"] / n) * b["absolute_gap"] for b in expected_bins) if n else 0.0
        expected_mce = max((b["absolute_gap"] for b in expected_bins), default=0.0)
        expected_status = "INSUFFICIENT_SAMPLE" if n < minimum_calibration_sample else "CALIBRATION_READY"
        if report["calibration_status"] != expected_status:
            raise ValueError("reported calibration_status contradicts the declared sample-size rule")

        reported_loss_raw = report["log_loss"]
        reported_loss = float(reported_loss_raw)
        if math.isnan(reported_loss) or reported_loss < 0.0:
            raise ValueError("reported log_loss must be non-negative and not NaN")
        actual_bins = report["bins"]
        if len(actual_bins) != len(expected_bins):
            raise ValueError("reported reliability-bin count differs from independent recomputation")
        errors: dict[str, float] = {
            "brier_score": abs(expected_brier - _number(report["brier_score"], "brier_score")),
            "log_loss": 0.0 if expected_loss == reported_loss else math.inf,
            "expected_calibration_error": abs(expected_ece - _number(report["expected_calibration_error"], "expected_calibration_error")),
            "maximum_calibration_error": abs(expected_mce - _number(report["maximum_calibration_error"], "maximum_calibration_error")),
        }
        if math.isfinite(expected_loss) and math.isfinite(reported_loss):
            errors["log_loss"] = abs(expected_loss - reported_loss)
        for i, (expected_bin, actual_bin) in enumerate(zip(expected_bins, actual_bins)):
            for field, expected_value in expected_bin.items():
                key = f"bins[{i}].{field}"
                actual_value = actual_bin[field]
                if field == "count":
                    errors[key] = 0.0 if int(actual_value) == expected_value else math.inf
                else:
                    errors[key] = abs(float(expected_value) - _number(actual_value, key))
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return MathematicalAudit(
            "probability_calibration",
            AuditStatus.INVALID_INPUT,
            "calibration replay inputs",
            None,
            None,
            None,
            tolerance,
            (),
            f"Cannot independently verify calibration report: {exc}",
        )

    worst = max(errors, key=errors.get)
    worst_error = errors[worst]
    status = AuditStatus.VERIFIED if all(error <= tolerance for error in errors.values()) else AuditStatus.FALSIFIED
    return MathematicalAudit(
        "probability_calibration",
        status,
        worst,
        None if math.isinf(worst_error) else (
            expected_loss if worst == "log_loss" else
            expected_brier if worst == "brier_score" else
            expected_ece if worst == "expected_calibration_error" else
            expected_mce if worst == "maximum_calibration_error" else None
        ),
        None if math.isinf(worst_error) else float(report.get(worst, 0.0)) if worst in report else None,
        worst_error,
        tolerance,
        (
            "raw assessments and observed outcomes are the exact paired sample",
            "class order is bullish, bearish, neutral",
            "reliability bins use maximum predicted probability and deterministic equal-width bins",
            "the declared minimum sample threshold is the intended calibration-readiness rule",
        ),
        (
            "Calibration scores and reliability bins match an independent recomputation. This does not prove predictive validity, sample independence, or absence of data leakage."
            if status is AuditStatus.VERIFIED
            else f"Independent recomputation contradicts report field {worst}; the numerical claim is falsified."
        ),
    )
