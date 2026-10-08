"""Contracts, enums, and dataclasses for the Decision Intelligence Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvidenceSource(str, Enum):
    MARKET_MEMORY = "MarketMemory"
    EXPERIMENT = "Experiment"
    VALIDATION = "Validation"
    MACRO_INTELLIGENCE = "MacroIntelligence"
    RESEARCH_OBJECTS = "ResearchObjects"
    QUANT_ENGINE = "QuantEngine"


class ProbabilityDirection(str, Enum):
    BULLISH = "Bullish"
    BEARISH = "Bearish"
    NEUTRAL = "Neutral"


class ProbabilityOutcome(str, Enum):
    BULLISH = "Bullish"
    BEARISH = "Bearish"
    NEUTRAL = "Neutral"


class CalculationMethod(str, Enum):
    WEIGHTED_EVIDENCE = "WeightedEvidence"
    BAYESIAN = "Bayesian"
    HISTORICAL_FREQUENCY = "HistoricalFrequency"
    CONFIDENCE_ADJUSTED = "ConfidenceAdjusted"
    EVIDENCE_BALANCE = "EvidenceBalance"
    CALIBRATED_LINEAR_POOL = "CalibratedLinearPool"


class DecisionStatus(str, Enum):
    PENDING = "Pending"
    EVIDENCE_COLLECTED = "EvidenceCollected"
    SCORED = "Scored"
    PROBABILITY_COMPUTED = "ProbabilityComputed"
    REASONED = "Reasoned"
    REPORT_GENERATED = "ReportGenerated"
    ARCHIVED = "Archived"


class DecisionVersion(str, Enum):
    DECISION_V1 = "DECISION_V1"


@dataclass
class DecisionEvidenceItem:
    """Canonical decision evidence item with optional structured provenance."""

    source: EvidenceSource
    source_id: str
    direction: ProbabilityOutcome
    strength: float
    weight: float
    confidence: float
    description: str
    supporting_ids: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "source": self.source.value,
            "source_id": self.source_id,
            "direction": self.direction.value,
            "strength": self.strength,
            "weight": self.weight,
            "confidence": self.confidence,
            "description": self.description,
            "supporting_ids": list(self.supporting_ids),
        }
        if self.provenance:
            data["provenance"] = self.provenance
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionEvidenceItem:
        return cls(
            source=EvidenceSource(data["source"]),
            source_id=data["source_id"],
            direction=ProbabilityOutcome(data["direction"]),
            strength=float(data["strength"]),
            weight=float(data["weight"]),
            confidence=float(data["confidence"]),
            description=data.get("description", ""),
            supporting_ids=list(data.get("supporting_ids", [])),
            provenance=dict(data.get("provenance", {})),
        )


EvidenceItem = DecisionEvidenceItem


@dataclass
class WeightConfiguration:
    macro_weight: float = 0.25
    market_memory_weight: float = 0.25
    experiment_weight: float = 0.20
    validation_weight: float = 0.15
    quant_weight: float = 0.15
    weighting_version: str = "WEIGHT_V1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "macro_weight": self.macro_weight,
            "market_memory_weight": self.market_memory_weight,
            "experiment_weight": self.experiment_weight,
            "validation_weight": self.validation_weight,
            "quant_weight": self.quant_weight,
            "weighting_version": self.weighting_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WeightConfiguration:
        return cls(
            macro_weight=float(data.get("macro_weight", 0.25)),
            market_memory_weight=float(data.get("market_memory_weight", 0.25)),
            experiment_weight=float(data.get("experiment_weight", 0.20)),
            validation_weight=float(data.get("validation_weight", 0.15)),
            quant_weight=float(data.get("quant_weight", 0.15)),
            weighting_version=str(data.get("weighting_version", "WEIGHT_V1")),
        )

    def total_weight(self) -> float:
        return self.macro_weight + self.market_memory_weight + self.experiment_weight + self.validation_weight + self.quant_weight
