"""Deterministic, outcome-grounded probability calibration."""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from math import exp, isfinite, log
from typing import Dict, List, Tuple

from researchos.objects.evidence import EvidenceRegistry


@dataclass(frozen=True)
class CalibrationReport:
    """Immutable calibration result."""

    research_id: str
    calibration_method: str
    total_samples: int
    calibrated_map: Dict[str, float]
    expected_calibration_error: float
    brier_score: float
    outcome_rate: float

    def get_calibrated_probability(self, evidence_id: str) -> float:
        if evidence_id not in self.calibrated_map:
            raise KeyError(f"Unknown calibrated evidence id: {evidence_id}")
        return self.calibrated_map[evidence_id]


class ProbabilityCalibrator:
    """Fit isotonic PAVA or Platt scaling from explicit historical outcomes."""

    MIN_SAMPLES = 10

    def __init__(self, method: str = "isotonic") -> None:
        if method not in ("isotonic", "platt"):
            raise ValueError("Method must be 'isotonic' or 'platt'")
        self.method = method
        self._is_fitted = False
        self._model: object | None = None
        self._outcomes: Dict[str, float] = {}
        self._fitted_ids: Tuple[str, ...] = ()
        self._isotonic_breakpoints: Tuple[tuple[float, float], ...] = ()

    @staticmethod
    def _matched(
        registry: EvidenceRegistry, outcomes: Dict[str, bool]
    ) -> List[tuple[str, float, float]]:
        evidence_by_id = {e.id: e for e in registry.evidence}
        matched_ids = [eid for eid in sorted(outcomes) if eid in evidence_by_id]
        invalid_ids = [
            eid for eid in matched_ids
            if not isinstance(outcomes[eid], bool)
        ]
        if invalid_ids:
            raise ValueError(
                "Calibration outcomes must be booleans for matched evidence IDs; "
                f"invalid IDs: {invalid_ids[:5]}"
            )
        rows = [
            (eid, evidence_by_id[eid].confidence, 1.0 if outcomes[eid] else 0.0)
            for eid in matched_ids
        ]
        if len(rows) < ProbabilityCalibrator.MIN_SAMPLES:
            raise ValueError("At least 10 matched evidence/outcome samples are required.")
        labels = {row[2] for row in rows}
        if labels != {0.0, 1.0}:
            raise ValueError("Calibration requires both positive and negative outcomes.")
        return rows

    @staticmethod
    def _isotonic(
        rows: List[tuple[str, float, float]],
    ) -> tuple[Dict[str, float], Tuple[tuple[float, float], ...]]:
        """Fit PAVA and return both training predictions and confidence breakpoints."""
        ordered = sorted(rows, key=lambda r: (r[1], r[0]))
        grouped: List[list[float | int]] = []
        for _, x, y in ordered:
            if grouped and float(grouped[-1][0]) == x:
                grouped[-1][1] = int(grouped[-1][1]) + 1
                grouped[-1][2] = float(grouped[-1][2]) + y
            else:
                grouped.append([x, 1, y])

        # Equal confidence values must share one empirical rate before PAVA;
        # otherwise tie ordering can assign different labels to the same x.
        blocks: List[list[float | int]] = []
        for x, count, positives in grouped:
            blocks.append([x, count, positives])
            while len(blocks) >= 2:
                a, b = blocks[-2], blocks[-1]
                if float(a[2]) / int(a[1]) <= float(b[2]) / int(b[1]):
                    break
                blocks[-2:] = [[
                    min(float(a[0]), float(b[0])),
                    int(a[1]) + int(b[1]),
                    float(a[2]) + float(b[2]),
                ]]

        breakpoints: List[tuple[float, float]] = []
        probability_by_confidence: Dict[float, float] = {}
        for x, count, positives in blocks:
            p = round(max(0.0, min(1.0, float(positives) / int(count))), 10)
            breakpoints.append((float(x), p))
            probability_by_confidence[float(x)] = p
        predictions = {
            eid: probability_by_confidence[x]
            for eid, x, _ in rows
        }
        return predictions, tuple(breakpoints)

    @staticmethod
    def _sigmoid(z: float) -> float:
        if z >= 0.0:
            return 1.0 / (1.0 + exp(-z))
        ez = exp(z)
        return ez / (1.0 + ez)

    @classmethod
    def _platt(cls, rows: List[tuple[str, float, float]]) -> tuple[float, float]:
        """Deterministic Newton fit for y ~ sigmoid(a*x+b)."""
        positives = sum(y for _, _, y in rows)
        negatives = len(rows) - positives
        a, b = 0.0, log((positives + 0.5) / (negatives + 0.5))
        for _ in range(100):
            g1 = g2 = h11 = h12 = h22 = 0.0
            for _, x, y in rows:
                p = cls._sigmoid(a * x + b)
                w = max(p * (1.0 - p), 1e-12)
                err = p - y
                g1 += err * x
                g2 += err
                h11 += w * x * x
                h12 += w * x
                h22 += w
            det = h11 * h22 - h12 * h12
            if det <= 1e-14:
                break
            da = (h22 * g1 - h12 * g2) / det
            db = (-h12 * g1 + h11 * g2) / det
            da = max(-1.0, min(1.0, da))
            db = max(-1.0, min(1.0, db))
            a_new, b_new = a - da, b - db
            if abs(a_new - a) + abs(b_new - b) < 1e-12:
                a, b = a_new, b_new
                break
            a, b = a_new, b_new
        return a, b

    def fit(
        self, evidence_registry: EvidenceRegistry, ground_truth_outcomes: Dict[str, bool]
    ) -> None:
        rows = self._matched(evidence_registry, ground_truth_outcomes)
        if self.method == "isotonic":
            self._model, self._isotonic_breakpoints = self._isotonic(rows)
        else:
            self._model = self._platt(rows)
            self._isotonic_breakpoints = ()
        self._outcomes = {eid: y for eid, _, y in rows}
        self._fitted_ids = tuple(eid for eid, _, _ in rows)
        self._is_fitted = True

    def predict_probability(self, confidence: float) -> float:
        """Predict calibrated probability for any confidence after fitting.

        For isotonic calibration, unseen out-of-sample confidence values are mapped
        using the fitted monotone step function with clipped out-of-range behavior.
        This method never uses future outcome labels.
        """
        if not self._is_fitted:
            raise RuntimeError("Calibrator must be fitted before predicting.")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not isfinite(confidence)
            or not 0.0 <= confidence <= 1.0
        ):
            raise ValueError("confidence must be finite and between 0 and 1")

        if self.method == "isotonic":
            if not self._isotonic_breakpoints:
                raise RuntimeError("Isotonic model has no fitted breakpoints.")
            xs = tuple(x for x, _ in self._isotonic_breakpoints)
            index = bisect_right(xs, confidence) - 1
            if index < 0:
                index = 0
            return self._isotonic_breakpoints[index][1]

        assert isinstance(self._model, tuple)
        a, b = self._model
        return round(max(0.0, min(1.0, self._sigmoid(a * confidence + b))), 10)

    def _predict(self, evidence_id: str, confidence: float) -> float:
        """Backward-compatible internal prediction by evidence id."""
        if self.method == "isotonic":
            return self.predict_probability(confidence)
        return self.predict_probability(confidence)

    def calibrate(self, evidence_registry: EvidenceRegistry) -> CalibrationReport:
        if not self._is_fitted:
            raise RuntimeError("Calibrator must be fitted before calibrating.")
        evidence_by_id = {e.id: e for e in evidence_registry.evidence}
        matched_ids = [eid for eid in self._fitted_ids if eid in evidence_by_id]
        if not matched_ids:
            raise ValueError("No fitted evidence is present in the supplied registry.")
        calibrated = {
            eid: self._predict(eid, evidence_by_id[eid].confidence) for eid in matched_ids
        }
        n = len(matched_ids)
        bins: Dict[int, list[str]] = {}
        for eid in matched_ids:
            p = calibrated[eid]
            bins.setdefault(min(9, int(p * 10)), []).append(eid)
        ece = 0.0
        brier = 0.0
        for ids in bins.values():
            mean_p = sum(calibrated[eid] for eid in ids) / len(ids)
            mean_y = sum(self._outcomes[eid] for eid in ids) / len(ids)
            ece += len(ids) / n * abs(mean_p - mean_y)
        for eid in matched_ids:
            p = calibrated[eid]
            y = self._outcomes[eid]
            brier += (p - y) ** 2
        rate = sum(self._outcomes[eid] for eid in matched_ids) / n
        return CalibrationReport(
            research_id=evidence_registry.research_id,
            calibration_method=self.method,
            total_samples=n,
            calibrated_map=calibrated,
            expected_calibration_error=round(ece, 10),
            brier_score=round(brier / n, 10),
            outcome_rate=round(rate, 10),
        )

    def generate_report(self, report: CalibrationReport, registry: EvidenceRegistry) -> str:
        lines = [
            "=" * 80,
            " PROBABILITY CALIBRATION REPORT",
            "=" * 80,
            f"Research ID: {report.research_id}",
            f"Method: {report.calibration_method.upper()}",
            f"Matched samples: {report.total_samples}",
            f"Outcome rate: {report.outcome_rate:.6f}",
            f"ECE: {report.expected_calibration_error:.6f}",
            f"Brier score: {report.brier_score:.6f}",
            "",
            "CALIBRATED EVIDENCE MAPPING:",
            "-" * 80,
        ]
        evidence_by_id = {e.id: e for e in registry.evidence}
        for eid, probability in sorted(report.calibrated_map.items()):
            ev = evidence_by_id.get(eid)
            if ev:
                lines.append(
                    f"  Evidence: {eid[:8]}... | Heuristic: {ev.confidence:.4f} "
                    f"-> Calibrated: {probability:.4f} | Direction: {ev.direction}"
                )
        lines.append("=" * 80)
        return "\n".join(lines)
