"""
Phase 7.3 — Probability Assessment Layer

Deterministic aggregation of validated decision evidence into probability
estimates. Calibration quality is optional evidence metadata: this module never
infers or fabricates a calibration status.
"""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any

from researchos.core.base_object import BaseObject
from researchos.core.identity import deterministic_hash, generate_id
from researchos.core.lifecycle import LifecycleStage
from researchos.core.timestamp import parse_timestamp, utc_now
from researchos.decision_engine.contracts import (
    CalculationMethod,
    DecisionEvidenceItem,
    ProbabilityOutcome,
)
from researchos.decision_engine.evidence import EvidenceCollection

CALCULATION_VERSION = "PROBABILITY_V1"
FLOAT_TOLERANCE = 1e-9
_DIRECTION_BULLISH = "bullish"
_DIRECTION_BEARISH = "bearish"
_UNIFORM_PROBABILITY = 1.0 / 3.0


def _normalize_direction(direction: Any) -> str:
    return str(direction).strip().lower()


class ProbabilityAssessment(BaseObject):
    """Deterministic probability assessment derived from evidence items."""

    def __init__(
        self,
        decision_context_id: str,
        evidence_collection_id: str,
        bullish_probability: float = 0.0,
        bearish_probability: float = 0.0,
        neutral_probability: float = 0.0,
        confidence: float = 0.0,
        uncertainty: float = 0.0,
        evidence_strength: float = 0.0,
        historical_consistency: float = 0.0,
        sample_size: int = 0,
        calculation_method: CalculationMethod = CalculationMethod.WEIGHTED_EVIDENCE,
        calculation_version: str = CALCULATION_VERSION,
        limitations: list[str] | None = None,
        timestamp: datetime | None = None,
        ontology_tags: list[str] | None = None,
        id: str | None = None,
        probability_calibration_status: str | None = None,
    ):
        if id is None:
            id = generate_id(
                f"ProbabilityAssessment|{decision_context_id}|{evidence_collection_id}"
            )
        super().__init__(id=id, ontology_tags=ontology_tags)
        self.decision_context_id = decision_context_id
        self.evidence_collection_id = evidence_collection_id
        self.bullish_probability = float(bullish_probability)
        self.bearish_probability = float(bearish_probability)
        self.neutral_probability = float(neutral_probability)
        self.confidence = float(confidence)
        self.uncertainty = float(uncertainty)
        self.evidence_strength = float(evidence_strength)
        self.historical_consistency = float(historical_consistency)
        self.sample_size = int(sample_size)
        self.calculation_method = calculation_method
        self.calculation_version = calculation_version
        self.limitations = list(limitations) if limitations else []
        self.timestamp = timestamp or utc_now()
        self.probability_calibration_status = (
            str(probability_calibration_status).strip()
            if probability_calibration_status is not None
            else None
        ) or None
        self._assessment_hash = ""
        self._update_hash()
        self.lifecycle.transition(
            LifecycleStage.ANALYZED,
            reason=(
                f"Probability assessed: B={self.bullish_probability:.4f}, "
                f"Be={self.bearish_probability:.4f}, N={self.neutral_probability:.4f}, "
                f"confidence={self.confidence:.4f}, sample_size={self.sample_size}"
            ),
        )

    def with_calibration_status(self, status: str) -> "ProbabilityAssessment":
        """Return an immutable-equivalent assessment carrying governed calibration evidence."""
        normalized = str(status).strip()
        if not normalized:
            raise ValueError("calibration status must not be empty")
        return ProbabilityAssessment(
            decision_context_id=self.decision_context_id,
            evidence_collection_id=self.evidence_collection_id,
            bullish_probability=self.bullish_probability,
            bearish_probability=self.bearish_probability,
            neutral_probability=self.neutral_probability,
            confidence=self.confidence,
            uncertainty=self.uncertainty,
            evidence_strength=self.evidence_strength,
            historical_consistency=self.historical_consistency,
            sample_size=self.sample_size,
            calculation_method=self.calculation_method,
            calculation_version=self.calculation_version,
            limitations=list(self.limitations),
            timestamp=self.timestamp,
            ontology_tags=list(self.ontology_tags),
            id=self.id,
            probability_calibration_status=normalized,
        )

    @property
    def assessment_hash(self) -> str:
        if not self._assessment_hash:
            self._update_hash()
        return self._assessment_hash

    def _update_hash(self) -> None:
        self._assessment_hash = deterministic_hash(self._to_hashable_dict())

    def _to_hashable_dict(self) -> dict[str, Any]:
        return {
            "decision_context_id": self.decision_context_id,
            "evidence_collection_id": self.evidence_collection_id,
            "bullish_probability": self.bullish_probability,
            "bearish_probability": self.bearish_probability,
            "neutral_probability": self.neutral_probability,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "evidence_strength": self.evidence_strength,
            "historical_consistency": self.historical_consistency,
            "sample_size": self.sample_size,
            "calculation_method": self.calculation_method.value,
            "calculation_version": self.calculation_version,
            "limitations": sorted(self.limitations),
            "ontology_tags": sorted(self.ontology_tags),
            "probability_calibration_status": self.probability_calibration_status,
        }

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update(
            {
                "decision_context_id": self.decision_context_id,
                "evidence_collection_id": self.evidence_collection_id,
                "bullish_probability": self.bullish_probability,
                "bearish_probability": self.bearish_probability,
                "neutral_probability": self.neutral_probability,
                "confidence": self.confidence,
                "uncertainty": self.uncertainty,
                "evidence_strength": self.evidence_strength,
                "historical_consistency": self.historical_consistency,
                "sample_size": self.sample_size,
                "calculation_method": self.calculation_method.value,
                "calculation_version": self.calculation_version,
                "limitations": self.limitations,
                "timestamp": self.timestamp.isoformat(),
                "assessment_hash": self._assessment_hash,
            }
        )
        if self.probability_calibration_status is not None:
            base["probability_calibration_status"] = self.probability_calibration_status
        return base

    def validate_integrity(self) -> None:
        """Fail closed when the serialized assessment hash does not match its content."""
        expected = deterministic_hash(self._to_hashable_dict())
        if not self._assessment_hash:
            raise ValueError("probability assessment is missing assessment_hash")
        if self._assessment_hash != expected:
            raise ValueError("probability assessment assessment_hash does not match content")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProbabilityAssessment":
        obj = super().from_dict(data)  # type: ignore[assignment]
        obj.decision_context_id = data["decision_context_id"]
        obj.evidence_collection_id = data["evidence_collection_id"]
        obj.bullish_probability = float(data.get("bullish_probability", 0.0))
        obj.bearish_probability = float(data.get("bearish_probability", 0.0))
        obj.neutral_probability = float(data.get("neutral_probability", 0.0))
        obj.confidence = float(data.get("confidence", 0.0))
        obj.uncertainty = float(data.get("uncertainty", 0.0))
        obj.evidence_strength = float(data.get("evidence_strength", 0.0))
        obj.historical_consistency = float(data.get("historical_consistency", 0.0))
        obj.sample_size = int(data.get("sample_size", 0))
        obj.calculation_method = CalculationMethod(
            data.get("calculation_method", CalculationMethod.WEIGHTED_EVIDENCE.value)
        )
        obj.calculation_version = data.get("calculation_version", CALCULATION_VERSION)
        obj.limitations = list(data.get("limitations", []))
        ts = data.get("timestamp")
        obj.timestamp = parse_timestamp(ts) if ts else utc_now()
        obj.probability_calibration_status = data.get("probability_calibration_status")
        obj._assessment_hash = data.get("assessment_hash", "")
        if obj._assessment_hash:
            obj.validate_integrity()
        return obj


class ProbabilityCalculator:
    """Stateless pure aggregation of DecisionEvidenceItem fields."""

    def __init__(self, calculation_version: str = CALCULATION_VERSION):
        self.calculation_version = calculation_version

    def calculate(self, collection: EvidenceCollection) -> ProbabilityAssessment:
        return self._aggregate(
            collection.decision_context_id,
            collection.id,
            collection.items,
            collection.collection_timestamp,
        )

    def compute(
        self,
        decision_context_id: str,
        evidence_collection_id: str,
        items: list[DecisionEvidenceItem],
        timestamp: datetime | None = None,
    ) -> ProbabilityAssessment:
        return self._aggregate(decision_context_id, evidence_collection_id, items, timestamp)

    def _aggregate(
        self,
        decision_context_id: str,
        evidence_collection_id: str,
        items: list[DecisionEvidenceItem],
        timestamp: datetime | None = None,
    ) -> ProbabilityAssessment:
        bullish_weight = bearish_weight = neutral_weight = 0.0
        confidences: list[float] = []
        weighted_contributions: list[float] = []
        for item in items:
            confidence = float(item.confidence)
            contribution = confidence * float(item.weight)
            confidences.append(confidence)
            weighted_contributions.append(contribution)
            direction = _normalize_direction(
                item.direction.value
                if isinstance(item.direction, ProbabilityOutcome)
                else item.direction
            )
            if direction == _DIRECTION_BULLISH:
                bullish_weight += contribution
            elif direction == _DIRECTION_BEARISH:
                bearish_weight += contribution
            else:
                neutral_weight += contribution
        total = bullish_weight + bearish_weight + neutral_weight
        if total > 0:
            bullish_probability = bullish_weight / total
            bearish_probability = bearish_weight / total
            neutral_probability = neutral_weight / total
        else:
            bullish_probability = bearish_probability = neutral_probability = _UNIFORM_PROBABILITY
        neutral_probability = max(0.0, 1.0 - bullish_probability - bearish_probability)
        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        evidence_strength = (
            sum(weighted_contributions) / len(weighted_contributions)
            if weighted_contributions
            else 0.0
        )
        sample_size = len(items)
        historical_consistency = max(bullish_probability, bearish_probability, neutral_probability)
        uncertainty = 1.0 - historical_consistency
        limitations = self._derive_limitations(items, sample_size, total, confidence, uncertainty)
        return ProbabilityAssessment(
            decision_context_id=decision_context_id,
            evidence_collection_id=evidence_collection_id,
            bullish_probability=bullish_probability,
            bearish_probability=bearish_probability,
            neutral_probability=neutral_probability,
            confidence=confidence,
            uncertainty=uncertainty,
            evidence_strength=evidence_strength,
            historical_consistency=historical_consistency,
            sample_size=sample_size,
            calculation_method=CalculationMethod.WEIGHTED_EVIDENCE,
            calculation_version=self.calculation_version,
            limitations=limitations,
            timestamp=timestamp,
        )

    @staticmethod
    def _derive_limitations(
        items: list[DecisionEvidenceItem],
        sample_size: int,
        total: float,
        confidence: float,
        uncertainty: float,
    ) -> list[str]:
        limitations: list[str] = []
        if sample_size == 0:
            limitations.append("No evidence items available for probability assessment")
            return limitations
        if sample_size < 3:
            limitations.append(f"Low evidence sample size: {sample_size} items")
        if total == 0:
            limitations.append(
                "All evidence items have zero effective weight (confidence * weight = 0)"
            )
        if confidence == 0.0:
            limitations.append("No confident evidence; all items have zero confidence")
        if uncertainty > 0.6:
            limitations.append("High uncertainty: evidence directions are widely dispersed")
        return limitations


class ProbabilityValidator:
    """Validates probability assessment invariants with legacy-compatible APIs."""

    def validate(self, assessment: ProbabilityAssessment) -> list[str]:
        """Return validation errors; an empty list means the assessment is valid."""
        errors: list[str] = []
        probabilities = [
            assessment.bullish_probability,
            assessment.bearish_probability,
            assessment.neutral_probability,
        ]
        if any(p < 0.0 or p > 1.0 for p in probabilities):
            errors.append("probabilities must be in [0, 1]")
        if abs(sum(probabilities) - 1.0) > FLOAT_TOLERANCE:
            errors.append("probabilities must sum to 1.0")
        if not 0.0 <= assessment.confidence <= 1.0:
            errors.append("confidence must be in [0, 1]")
        if not 0.0 <= assessment.uncertainty <= 1.0:
            errors.append("uncertainty must be in [0, 1]")
        if assessment.sample_size < 0:
            errors.append("sample_size must be non-negative")
        return errors

    def is_valid(self, assessment: ProbabilityAssessment) -> bool:
        """Return True when no probability assessment invariant is violated."""
        return self.validate(assessment) == []


class CalibratedLinearPool:
    """Fuse validated three-way probability distributions with a linear opinion pool.

    Component probabilities must be explicitly marked as out-of-sample
    calibrated. Confidence scores are never converted into probabilities.
    """

    VERSION = "CALIBRATED_LINEAR_POOL_V1"

    @staticmethod
    def _distribution(item: DecisionEvidenceItem) -> tuple[float, float, float]:
        provenance = item.provenance or {}
        if provenance.get("calibration_status") != "validated":
            raise ValueError(
                f"evidence {item.source_id!r} is not backed by validated calibration"
            )
        raw = provenance.get("probability_distribution")
        if not isinstance(raw, dict):
            raise ValueError(
                f"evidence {item.source_id!r} is missing probability_distribution"
            )
        values = (
            float(raw.get("bullish", math.nan)),
            float(raw.get("bearish", math.nan)),
            float(raw.get("neutral", math.nan)),
        )
        if any(not math.isfinite(v) or v < 0.0 or v > 1.0 for v in values):
            raise ValueError(f"evidence {item.source_id!r} contains invalid probability values")
        if abs(sum(values) - 1.0) > FLOAT_TOLERANCE:
            raise ValueError(f"evidence {item.source_id!r} probabilities must sum to 1.0")
        return values

    def fuse(self, decision_context_id: str, evidence_collection_id: str,
             items: list[DecisionEvidenceItem], timestamp: datetime | None = None
    ) -> ProbabilityAssessment:
        if not items:
            raise ValueError("calibrated linear pool requires at least one evidence item")
        weighted: list[tuple[float, tuple[float, float, float]]] = []
        for item in items:
            weight = float(item.weight)
            if not math.isfinite(weight) or weight < 0.0:
                raise ValueError(f"evidence {item.source_id!r} has invalid fusion weight")
            weighted.append((weight, self._distribution(item)))
        total_weight = sum(weight for weight, _ in weighted)
        if total_weight <= 0.0:
            raise ValueError("calibrated linear pool requires positive total weight")
        bullish = sum(w * d[0] for w, d in weighted) / total_weight
        bearish = sum(w * d[1] for w, d in weighted) / total_weight
        neutral = sum(w * d[2] for w, d in weighted) / total_weight
        total = bullish + bearish + neutral
        if not math.isfinite(total) or total <= 0.0:
            raise ValueError("fused probability distribution is invalid")
        bullish /= total
        bearish /= total
        neutral /= total
        return ProbabilityAssessment(
            decision_context_id=decision_context_id,
            evidence_collection_id=evidence_collection_id,
            bullish_probability=bullish,
            bearish_probability=bearish,
            neutral_probability=neutral,
            confidence=max(bullish, bearish, neutral),
            uncertainty=1.0 - max(bullish, bearish, neutral),
            evidence_strength=total_weight / len(weighted),
            historical_consistency=max(bullish, bearish, neutral),
            sample_size=len(items),
            calculation_method=CalculationMethod.CALIBRATED_LINEAR_POOL,
            calculation_version=self.VERSION,
            limitations=[
                "Components must be calibrated out-of-sample",
                "Fusion does not assume component independence",
                "Evidence dependence must be monitored separately",
            ],
            timestamp=timestamp,
            probability_calibration_status="validated_components",
        )



__all__ = [
    "CALCULATION_VERSION",
    "FLOAT_TOLERANCE",
    "ProbabilityAssessment",
    "ProbabilityCalculator",
    "ProbabilityValidator",
    "CalibratedLinearPool",
]
