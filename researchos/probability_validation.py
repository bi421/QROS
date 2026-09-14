"""Deterministic validation and calibration diagnostics for probability outputs.

Phase 5 deliberately separates *validation* from *calibration*.  The module
never changes a probability and never fits an ML model.  It evaluates already
produced ProbabilityAssessment objects against observed outcomes so that
calibration quality can be measured before probability is consumed by risk.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Literal, Sequence

from researchos.decision_engine.probability import ProbabilityAssessment

PROBABILITY_VALIDATION_SCHEMA_VERSION = "probability-validation.v1"
ProbabilityOutcome = Literal["bullish", "bearish", "neutral"]
CalibrationStatus = Literal[
    "INSUFFICIENT_SAMPLE",
    "NOT_CALIBRATED",
    "CALIBRATION_READY",
]

_OUTCOMES: tuple[ProbabilityOutcome, ...] = ("bullish", "bearish", "neutral")


@dataclass(frozen=True)
class CalibrationBin:
    """Deterministic reliability-bin summary."""

    lower_bound: float
    upper_bound: float
    count: int
    mean_predicted_probability: float
    observed_frequency: float
    absolute_gap: float


@dataclass(frozen=True)
class ProbabilityValidationReport:
    """Immutable validation report for a batch of probability assessments."""

    schema_version: str
    assessment_count: int
    outcome_count: int
    brier_score: float
    log_loss: float
    expected_calibration_error: float
    maximum_calibration_error: float
    calibration_status: CalibrationStatus
    bins: tuple[CalibrationBin, ...]
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != PROBABILITY_VALIDATION_SCHEMA_VERSION:
            raise ValueError("unsupported probability validation schema version")
        if self.assessment_count < 0 or self.outcome_count < 0:
            raise ValueError("counts cannot be negative")
        if self.assessment_count != self.outcome_count:
            raise ValueError("assessment_count must equal outcome_count")
        if not 0.0 <= self.brier_score <= 2.0:
            raise ValueError("brier_score must be in [0, 2]")
        if self.log_loss < 0.0:
            raise ValueError("log_loss must be non-negative")
        if not 0.0 <= self.expected_calibration_error <= 1.0:
            raise ValueError("expected_calibration_error must be in [0, 1]")
        if not 0.0 <= self.maximum_calibration_error <= 1.0:
            raise ValueError("maximum_calibration_error must be in [0, 1]")

    @property
    def is_calibration_ready(self) -> bool:
        """Return whether the sample is large enough for calibration work."""
        return self.calibration_status == "CALIBRATION_READY"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "assessment_count": self.assessment_count,
            "outcome_count": self.outcome_count,
            "brier_score": self.brier_score,
            "log_loss": self.log_loss,
            "expected_calibration_error": self.expected_calibration_error,
            "maximum_calibration_error": self.maximum_calibration_error,
            "calibration_status": self.calibration_status,
            "bins": [
                {
                    "lower_bound": item.lower_bound,
                    "upper_bound": item.upper_bound,
                    "count": item.count,
                    "mean_predicted_probability": item.mean_predicted_probability,
                    "observed_frequency": item.observed_frequency,
                    "absolute_gap": item.absolute_gap,
                }
                for item in self.bins
            ],
            "limitations": list(self.limitations),
        }


def validate_probability_assessment(assessment: ProbabilityAssessment) -> tuple[str, ...]:
    """Validate a single assessment without altering it."""
    probabilities = (
        assessment.bullish_probability,
        assessment.bearish_probability,
        assessment.neutral_probability,
    )
    errors: list[str] = []
    if any(not 0.0 <= probability <= 1.0 for probability in probabilities):
        errors.append("probabilities must be in [0, 1]")
    if abs(sum(probabilities) - 1.0) > 1e-9:
        errors.append("probabilities must sum to 1 within tolerance")
    if not 0.0 <= assessment.confidence <= 1.0:
        errors.append("confidence must be in [0, 1]")
    if not 0.0 <= assessment.uncertainty <= 1.0:
        errors.append("uncertainty must be in [0, 1]")
    if assessment.sample_size < 0:
        errors.append("sample_size cannot be negative")
    return tuple(errors)


def evaluate_probability_calibration(
    assessments: Sequence[ProbabilityAssessment],
    observed_outcomes: Sequence[str],
    *,
    bin_count: int = 10,
    minimum_calibration_sample: int = 30,
) -> ProbabilityValidationReport:
    """Evaluate multiclass probability quality against observed outcomes.

    Metrics are computed directly from the supplied probabilities:

    * multiclass Brier score;
    * multiclass log loss;
    * expected calibration error (ECE) using max-probability reliability bins;
    * maximum calibration error (MCE).

    No probability is recalibrated by this function.  A sample below
    ``minimum_calibration_sample`` is explicitly marked
    ``INSUFFICIENT_SAMPLE`` rather than being presented as calibrated.
    """
    if bin_count < 1:
        raise ValueError("bin_count must be >= 1")
    if minimum_calibration_sample < 1:
        raise ValueError("minimum_calibration_sample must be >= 1")
    if len(assessments) != len(observed_outcomes):
        raise ValueError("assessments and observed_outcomes must have equal length")

    n = len(assessments)
    limitations: list[str] = []
    validated: list[tuple[float, float, float]] = []
    actuals: list[ProbabilityOutcome] = []

    for index, (assessment, observed) in enumerate(zip(assessments, observed_outcomes)):
        errors = validate_probability_assessment(assessment)
        if errors:
            raise ValueError(f"assessment {index} is invalid: {'; '.join(errors)}")
        outcome = str(observed).strip().lower()
        if outcome not in _OUTCOMES:
            raise ValueError(f"unsupported observed outcome at index {index}: {observed!r}")
        validated.append(
            (
                assessment.bullish_probability,
                assessment.bearish_probability,
                assessment.neutral_probability,
            )
        )
        actuals.append(outcome)  # type: ignore[arg-type]

    if n == 0:
        limitations.append("No assessment/outcome pairs supplied")

    brier = 0.0
    loss = 0.0
    confidences: list[float] = []
    correctness: list[bool] = []
    for probabilities, actual in zip(validated, actuals):
        target_index = _OUTCOMES.index(actual)
        brier += sum((probability - (1.0 if i == target_index else 0.0)) ** 2 for i, probability in enumerate(probabilities))
        actual_probability = probabilities[target_index]
        loss += -log(actual_probability) if actual_probability > 0.0 else float("inf")
        predicted_index = max(range(3), key=lambda i: probabilities[i])
        confidences.append(probabilities[predicted_index])
        correctness.append(predicted_index == target_index)

    brier_score = brier / n if n else 0.0
    log_loss = loss / n if n else 0.0

    bins = _build_bins(confidences, correctness, bin_count)
    ece = sum((item.count / n) * item.absolute_gap for item in bins) if n else 0.0
    mce = max((item.absolute_gap for item in bins), default=0.0)

    if n < minimum_calibration_sample:
        status: CalibrationStatus = "INSUFFICIENT_SAMPLE"
        limitations.append(
            f"Calibration sample size {n} is below minimum {minimum_calibration_sample}"
        )
    else:
        status = "CALIBRATION_READY"
        limitations.append("Metrics are diagnostic only; no recalibration was fitted")

    return ProbabilityValidationReport(
        schema_version=PROBABILITY_VALIDATION_SCHEMA_VERSION,
        assessment_count=n,
        outcome_count=n,
        brier_score=brier_score,
        log_loss=log_loss,
        expected_calibration_error=ece,
        maximum_calibration_error=mce,
        calibration_status=status,
        bins=bins,
        limitations=tuple(limitations),
    )


def _build_bins(
    confidences: Sequence[float],
    correctness: Sequence[bool],
    bin_count: int,
) -> tuple[CalibrationBin, ...]:
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bin_count)]
    for confidence, correct in zip(confidences, correctness):
        index = min(int(confidence * bin_count), bin_count - 1)
        buckets[index].append((confidence, correct))

    result: list[CalibrationBin] = []
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        lower = index / bin_count
        upper = (index + 1) / bin_count
        mean_confidence = sum(item[0] for item in bucket) / len(bucket)
        accuracy = sum(1.0 for _, correct in bucket if correct) / len(bucket)
        result.append(
            CalibrationBin(
                lower_bound=lower,
                upper_bound=upper,
                count=len(bucket),
                mean_predicted_probability=mean_confidence,
                observed_frequency=accuracy,
                absolute_gap=abs(mean_confidence - accuracy),
            )
        )
    return tuple(result)
