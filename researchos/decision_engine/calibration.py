"""Canonical calibration governance for Decision Intelligence probabilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from researchos.experiments.phase51.contracts import CalibrationResult, Phase51Result


class CalibrationStatus(str, Enum):
    """Evidence-derived calibration states; absence is never treated as calibrated."""

    WELL_CALIBRATED = "Well-Calibrated"
    NEEDS_ADJUSTMENT = "Needs Adjustment"
    POORLY_CALIBRATED = "Poorly Calibrated"


class CalibrationGovernanceError(ValueError):
    """Raised when calibration evidence is missing or internally inconsistent."""


@dataclass(frozen=True)
class CalibrationEvidence:
    """Immutable calibration evidence attached to a probability assessment."""

    status: CalibrationStatus
    calibration_error: float | None
    brier_score: float
    avg_confidence: float
    avg_accuracy: float
    sample_size: int
    num_bins: int
    source_hash: str | None = None

    def validate(self) -> None:
        if self.calibration_error is not None and not 0.0 <= self.calibration_error <= 1.0:
            raise CalibrationGovernanceError("calibration_error must be in [0, 1]")
        for name, value in (
            ("brier_score", self.brier_score),
            ("avg_confidence", self.avg_confidence),
            ("avg_accuracy", self.avg_accuracy),
        ):
            if not 0.0 <= value <= 1.0:
                raise CalibrationGovernanceError(f"{name} must be in [0, 1]")
        if self.sample_size < 0:
            raise CalibrationGovernanceError("sample_size must be non-negative")
        if self.num_bins <= 0:
            raise CalibrationGovernanceError("num_bins must be positive")
        if self.status is CalibrationStatus.WELL_CALIBRATED and self.calibration_error is None:
            raise CalibrationGovernanceError(
                "Well-Calibrated requires an evidence-derived calibration error"
            )

    @classmethod
    def from_result(
        cls,
        result: CalibrationResult,
        *,
        source_hash: str | None = None,
    ) -> "CalibrationEvidence":
        status = result.calibration_status
        if status is None:
            raise CalibrationGovernanceError("calibration result has no calibration_status")
        try:
            parsed_status = CalibrationStatus(status)
        except ValueError as exc:
            raise CalibrationGovernanceError(
                f"unsupported calibration status: {status!r}"
            ) from exc
        table = result.reliability_table
        error = table.get("calibration_error")
        sample_size = int(table.get("n_actual", 0))
        evidence = cls(
            status=parsed_status,
            calibration_error=float(error) if error is not None else None,
            brier_score=float(result.brier_score),
            avg_confidence=float(result.avg_confidence),
            avg_accuracy=float(result.avg_accuracy),
            sample_size=sample_size,
            num_bins=int(result.num_bins),
            source_hash=source_hash,
        )
        evidence.validate()
        return evidence

    @classmethod
    def from_phase51(cls, result: Phase51Result) -> "CalibrationEvidence":
        if result.calibration is None:
            raise CalibrationGovernanceError(
                "Phase 5.1 result has no calibration evidence"
            )
        return cls.from_result(
            result.calibration,
            source_hash=result.reproducibility_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "status": self.status.value,
            "calibration_error": self.calibration_error,
            "brier_score": self.brier_score,
            "avg_confidence": self.avg_confidence,
            "avg_accuracy": self.avg_accuracy,
            "sample_size": self.sample_size,
            "num_bins": self.num_bins,
            "source_hash": self.source_hash,
        }


__all__ = [
    "CalibrationEvidence",
    "CalibrationGovernanceError",
    "CalibrationStatus",
]
