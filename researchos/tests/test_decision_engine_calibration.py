from __future__ import annotations

import pytest

from researchos.decision_engine.calibration import (
    CalibrationEvidence,
    CalibrationGovernanceError,
    CalibrationStatus,
)
from researchos.experiments.phase51.calibration import (
    CALIBRATION_STATUS_WELL_CALIBRATED,
    evaluate_calibration,
)


def _result():
    probs = [{-1: 0.05, 0: 0.10, 1: 0.85}] * 20
    actuals = [1] * 17 + [0] * 3
    return evaluate_calibration(probs, actuals, num_bins=10)


def test_phase51_calibration_becomes_canonical_evidence() -> None:
    result = _result()
    assert result.calibration_status == CALIBRATION_STATUS_WELL_CALIBRATED
    evidence = CalibrationEvidence.from_result(result, source_hash="phase51-hash")
    assert evidence.status is CalibrationStatus.WELL_CALIBRATED
    assert evidence.source_hash == "phase51-hash"
    assert evidence.sample_size == 4
    evidence.validate()


def test_missing_calibration_status_fails_closed() -> None:
    result = _result()
    table = dict(result.reliability_table)
    table.pop("calibration_status")
    from researchos.experiments.phase51.contracts import CalibrationResult
    incomplete = CalibrationResult(
        num_bins=result.num_bins,
        reliability_table=table,
        brier_score=result.brier_score,
        avg_confidence=result.avg_confidence,
        avg_accuracy=result.avg_accuracy,
    )
    with pytest.raises(CalibrationGovernanceError, match="no calibration_status"):
        CalibrationEvidence.from_result(incomplete)


def test_unknown_calibration_status_fails_closed() -> None:
    result = _result()
    from researchos.experiments.phase51.contracts import CalibrationResult
    invalid = CalibrationResult(
        num_bins=result.num_bins,
        reliability_table={**result.reliability_table, "calibration_status": "Invented"},
        brier_score=result.brier_score,
        avg_confidence=result.avg_confidence,
        avg_accuracy=result.avg_accuracy,
    )
    with pytest.raises(CalibrationGovernanceError, match="unsupported calibration status"):
        CalibrationEvidence.from_result(invalid)
