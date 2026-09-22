"""Chronological, outcome-grounded probability calibration for Phase 5.2.

The calibrator is deliberately separate from model fitting. It accepts an
earlier OOS calibration sample and a later evaluation sample, fits one scalar
temperature on the earlier sample only, and evaluates raw versus calibrated
probabilities on the later sample. No random split or future-label access is
performed here.

Temperature scaling is used because Phase 5.2 is multiclass (-1, 0, +1).
For probabilities p_k, calibration applies softmax(log(p_k) / T). T=1 is the
raw probability surface. The fit is deterministic and uses a bounded golden-
section search over a fixed interval.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, log
from typing import Mapping, Sequence

CLASSES = (-1, 0, 1)
EPSILON = 1e-12


@dataclass(frozen=True)
class CalibrationComparison:
    """Immutable raw-vs-calibrated OOS comparison."""

    method: str
    temperature: float
    calibration_samples: int
    evaluation_samples: int
    raw_brier: float
    calibrated_brier: float
    raw_log_loss: float
    calibrated_log_loss: float

    @property
    def brier_improved(self) -> bool:
        return self.calibrated_brier < self.raw_brier

    @property
    def log_loss_improved(self) -> bool:
        return self.calibrated_log_loss < self.raw_log_loss


def _validate_rows(probabilities: Sequence[Mapping[int, float]], labels: Sequence[float]) -> None:
    if len(probabilities) != len(labels):
        raise ValueError("probabilities and labels must have equal length")
    if not probabilities:
        raise ValueError("at least one probability row is required")
    for row in probabilities:
        values = [float(row.get(cls, 0.0)) for cls in CLASSES]
        if any(not isfinite(v) or v < 0.0 for v in values):
            raise ValueError("probabilities must be finite and non-negative")
        if sum(values) <= 0.0:
            raise ValueError("each probability row must have positive mass")
    for label in labels:
        if int(label) not in CLASSES or float(label) != int(label):
            raise ValueError(f"labels must be one of {CLASSES}")


def _normalise(row: Mapping[int, float]) -> tuple[float, float, float]:
    values = [max(EPSILON, float(row.get(cls, 0.0))) for cls in CLASSES]
    total = sum(values)
    return (values[0] / total, values[1] / total, values[2] / total)


def apply_temperature(probabilities: Sequence[Mapping[int, float]], temperature: float) -> list[dict[int, float]]:
    """Apply deterministic multiclass temperature scaling."""
    if not isfinite(temperature) or temperature <= 0.0:
        raise ValueError("temperature must be finite and > 0")
    calibrated: list[dict[int, float]] = []
    inverse = 1.0 / temperature
    for row in probabilities:
        probs = _normalise(row)
        logits = [log(p) * inverse for p in probs]
        peak = max(logits)
        exp_values = [exp(v - peak) for v in logits]
        total = sum(exp_values)
        calibrated.append({cls: exp_values[i] / total for i, cls in enumerate(CLASSES)})
    return calibrated


def _log_loss(probabilities: Sequence[Mapping[int, float]], labels: Sequence[float]) -> float:
    total = 0.0
    for row, label in zip(probabilities, labels):
        p = max(EPSILON, min(1.0, float(row[int(label)])))
        total -= log(p)
    return total / len(labels)


def _brier(probabilities: Sequence[Mapping[int, float]], labels: Sequence[float]) -> float:
    total = 0.0
    for row, label in zip(probabilities, labels):
        actual = int(label)
        total += sum((float(row.get(cls, 0.0)) - (1.0 if cls == actual else 0.0)) ** 2 for cls in CLASSES)
    return total / len(labels)


def fit_temperature(
    calibration_probabilities: Sequence[Mapping[int, float]],
    calibration_labels: Sequence[float],
    *,
    min_samples: int = 50,
) -> float:
    """Fit temperature using earlier OOS outcomes only."""
    _validate_rows(calibration_probabilities, calibration_labels)
    if len(calibration_labels) < min_samples:
        raise ValueError(f"at least {min_samples} calibration samples are required")
    if len(set(int(v) for v in calibration_labels)) < 2:
        raise ValueError("calibration requires at least two observed classes")

    def objective(temp: float) -> float:
        return _log_loss(apply_temperature(calibration_probabilities, temp), calibration_labels)

    left, right = 0.05, 20.0
    phi = (1.0 + 5.0 ** 0.5) / 2.0
    for _ in range(80):
        c = right - (right - left) / phi
        d = left + (right - left) / phi
        if objective(c) <= objective(d):
            right = d
        else:
            left = c
    return round((left + right) / 2.0, 10)


def calibrate_oos(
    calibration_probabilities: Sequence[Mapping[int, float]],
    calibration_labels: Sequence[float],
    evaluation_probabilities: Sequence[Mapping[int, float]],
    evaluation_labels: Sequence[float],
    *,
    min_calibration_samples: int = 50,
) -> CalibrationComparison:
    """Fit on earlier OOS data and evaluate only on a later OOS sample."""
    _validate_rows(calibration_probabilities, calibration_labels)
    _validate_rows(evaluation_probabilities, evaluation_labels)
    temperature = fit_temperature(
        calibration_probabilities,
        calibration_labels,
        min_samples=min_calibration_samples,
    )
    calibrated = apply_temperature(evaluation_probabilities, temperature)
    return CalibrationComparison(
        method="temperature_scaling",
        temperature=temperature,
        calibration_samples=len(calibration_labels),
        evaluation_samples=len(evaluation_labels),
        raw_brier=round(_brier(evaluation_probabilities, evaluation_labels), 10),
        calibrated_brier=round(_brier(calibrated, evaluation_labels), 10),
        raw_log_loss=round(_log_loss(evaluation_probabilities, evaluation_labels), 10),
        calibrated_log_loss=round(_log_loss(calibrated, evaluation_labels), 10),
    )


__all__ = ["CalibrationComparison", "apply_temperature", "calibrate_oos", "fit_temperature"]
