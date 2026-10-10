from __future__ import annotations

import pytest

from researchos.market_memory.probability_calibration import ProbabilityCalibrator
from researchos.objects.evidence import Evidence, EvidenceRegistry


def _registry() -> EvidenceRegistry:
    evidence = [
        Evidence(
            observation_id=f"obs-{i}",
            hypothesis_id="hypothesis-1",
            interpretation=f"sample-{i}",
            direction="Supporting" if i % 2 else "Contradicting",
            source_reliability=confidence,
            id=f"evidence-{i}",
        )
        for i, confidence in enumerate(
            (0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.55, 0.65, 0.80, 0.90, 0.95, 0.99)
        )
    ]
    return EvidenceRegistry("research-1", evidence=evidence)


def test_isotonic_predicts_unseen_out_of_sample_confidence() -> None:
    registry = _registry()
    outcomes = {
        f"evidence-{i}": i >= 6
        for i in range(12)
    }

    calibrator = ProbabilityCalibrator(method="isotonic")
    calibrator.fit(registry, outcomes)

    low = calibrator.predict_probability(0.07)
    middle = calibrator.predict_probability(0.72)
    high = calibrator.predict_probability(0.98)

    assert 0.0 <= low <= middle <= high <= 1.0
    assert low < high


def test_isotonic_prediction_does_not_require_oos_evidence_id() -> None:
    registry = _registry()
    outcomes = {f"evidence-{i}": i >= 6 for i in range(12)}

    calibrator = ProbabilityCalibrator(method="isotonic")
    calibrator.fit(registry, outcomes)

    assert calibrator.predict_probability(0.72) == calibrator.predict_probability(0.72)


@pytest.mark.parametrize("confidence", [True, False, float("nan"), float("inf"), float("-inf")])
def test_predict_probability_rejects_boolean_and_non_finite_confidence(confidence) -> None:
    registry = _registry()
    outcomes = {f"evidence-{i}": i >= 6 for i in range(12)}
    calibrator = ProbabilityCalibrator(method="isotonic")
    calibrator.fit(registry, outcomes)

    with pytest.raises(ValueError, match="confidence must be finite"):
        calibrator.predict_probability(confidence)


@pytest.mark.parametrize("invalid_outcome", [0, 1, "false", "true", None, 0.0, 1.0])
def test_fit_rejects_non_boolean_matched_outcomes(invalid_outcome) -> None:
    registry = _registry()
    outcomes = {f"evidence-{i}": i >= 6 for i in range(12)}
    outcomes["evidence-0"] = invalid_outcome
    calibrator = ProbabilityCalibrator(method="isotonic")

    with pytest.raises(ValueError, match="outcomes must be booleans"):
        calibrator.fit(registry, outcomes)


def test_fit_ignores_unmatched_outcome_ids() -> None:
    registry = _registry()
    outcomes = {f"evidence-{i}": i >= 6 for i in range(12)}
    outcomes["not-in-registry"] = "not-a-boolean"
    calibrator = ProbabilityCalibrator(method="isotonic")

    calibrator.fit(registry, outcomes)

    assert calibrator.predict_probability(0.72) >= 0.0


def test_isotonic_groups_identical_confidences_before_fitting() -> None:
    original = _registry()
    evidence = [
        Evidence(
            observation_id=f"obs-{i}",
            hypothesis_id="hypothesis-1",
            interpretation=f"sample-{i}",
            direction="Supporting" if i % 2 else "Contradicting",
            source_reliability=0.12345 if i in (0, 1) else item.confidence,
            id=item.id,
        )
        for i, item in enumerate(original.evidence)
    ]
    registry = EvidenceRegistry("research-1", evidence=evidence)
    outcomes = {f"evidence-{i}": i >= 6 for i in range(12)}
    outcomes["evidence-0"] = False
    outcomes["evidence-1"] = True

    calibrator = ProbabilityCalibrator(method="isotonic")
    calibrator.fit(registry, outcomes)
    report = calibrator.calibrate(registry)

    assert calibrator.predict_probability(0.12345) == 0.5
    assert report.calibrated_map["evidence-0"] == report.calibrated_map["evidence-1"]
