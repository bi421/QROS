"""
Evidence objects â€” interpreted observations that support or contradict hypotheses.

Based on Article XVII: Object Model â€” Evidence Layer.
Based on Article XVI: Scientific Reasoning Framework â€” Evidence Layer.

Evidence is an observation that has been interpreted and contextualized
to support or contradict a specific hypothesis. The key difference from
an observation is that evidence has been given meaning in context.
"""

from __future__ import annotations

from datetime import datetime

from researchos.core.base_object import BaseObject
from researchos.core.identity import generate_id
from researchos.core.lifecycle import LifecycleStage
from researchos.core.timestamp import days_between, format_timestamp, parse_timestamp, utc_now

# Evidence quality factors (Article XVI, Section 2.2)
SOURCE_RELIABILITY_WEIGHT = 0.20
RECENCY_WEIGHT = 0.20
RELEVANCE_WEIGHT = 0.20
CONSENSUS_WEIGHT = 0.20
STRUCTURAL_IMPORTANCE_WEIGHT = 0.15
QUALITY_FACTOR_WEIGHT = 0.05

# Evidence aging multipliers (Article XVI, Section 2.5)
AGING_FRESH_MAX_DAYS = 7
AGING_RECENT_MAX_DAYS = 30
AGING_MATURE_MAX_DAYS = 90
AGING_FRESH_MULTIPLIER = 1.0
AGING_RECENT_MULTIPLIER = 0.90
AGING_MATURE_MULTIPLIER = 0.75
AGING_STALE_MULTIPLIER = 0.50

# Evidence tiers (Article XVI, Section 2.7)
TIER_PRIMARY_MULTIPLIER = 1.0
TIER_SECONDARY_MULTIPLIER = 0.75
TIER_TERTIARY_MULTIPLIER = 0.50


class Evidence(BaseObject):
    """
    An observation that has been interpreted and contextualized.

    Based on Article XVII: Object Model â€” Evidence.

    Evidence quality is computed from 6 factors:
        Quality = Source_Reliability Ã— Recency Ã— Relevance Ã—
                  Consensus Ã— Structural_Importance Ã— Quality_Factor

    Attributes:
        observation_id: Link to source Observation
        hypothesis_id: Link to Hypothesis
        interpretation: How the observation is interpreted
        direction: Supporting, Contradicting, or Neutral
        quality: Computed quality score (0.0-1.0)
        confidence: Quality Ã— (1 - uncertainty)
        weight: Relative importance
        tier: Primary, Secondary, or Tertiary
        age_days: Days since observation
        aging_multiplier: Weight reduction for age
        dependencies: Other evidence IDs this depends on
        conflicts: Conflicting evidence IDs
    """

    def __init__(
        self,
        observation_id: str,
        hypothesis_id: str,
        interpretation: str,
        direction: str = "Neutral",
        source_reliability: float = 1.0,
        recency: float = 1.0,
        relevance: float = 1.0,
        consensus: float = 1.0,
        structural_importance: float = 1.0,
        quality_factor: float = 1.0,
        uncertainty: float = 0.0,
        tier: str = "Primary",
        observation_timestamp: datetime | None = None,
        dependencies: list[str] | None = None,
        conflicts: list[str] | None = None,
        ontology_tags: list[str] | None = None,
        id: str | None = None,
    ):
        if id is None:
            seed = f"Evidence|{observation_id}|{hypothesis_id}|{interpretation}"
            id = generate_id(seed)

        super().__init__(id=id, ontology_tags=ontology_tags)

        self.observation_id = observation_id
        self.hypothesis_id = hypothesis_id
        self.interpretation = interpretation
        self.direction = direction

        # Quality factors
        self.source_reliability = source_reliability
        self.recency = recency
        self.relevance = relevance
        self.consensus = consensus
        self.structural_importance = structural_importance
        self.quality_factor = quality_factor
        self.uncertainty = uncertainty

        # Computed properties
        self.tier = tier
        self.observation_timestamp = observation_timestamp or utc_now()
        self.dependencies: list[str] = dependencies or []
        self.conflicts: list[str] = conflicts or []

        # Compute deterministic quality and confidence (no time dependency)
        self.quality = self._compute_quality()
        self.confidence = self._compute_confidence()

        # Transition to validated
        self.lifecycle.transition(
            LifecycleStage.VALIDATED,
            reason="Evidence quality and confidence computed",
        )

    def _compute_quality(self) -> float:
        """
        Compute evidence quality from 6 factors.

        Quality = Source_Reliability Ã— Recency Ã— Relevance Ã—
                  Consensus Ã— Structural_Importance Ã— Quality_Factor
        """
        quality = self.source_reliability * self.recency * self.relevance * self.consensus * self.structural_importance * self.quality_factor
        return min(1.0, max(0.0, quality))

    def _compute_confidence(self) -> float:
        """
        Compute evidence confidence.

        Confidence = Quality Ã— (1.0 - Uncertainty)
        """
        return self.quality * (1.0 - self.uncertainty)

    VALID_DIRECTIONS = ("Supporting", "Contradicting", "Neutral")

    def validate(self) -> bool:
        """
        Validate this evidence's direction.

        Raises:
            ValueError: If direction is not one of Supporting/Contradicting/Neutral.
        """
        if self.direction not in self.VALID_DIRECTIONS:
            raise ValueError(f"Evidence direction must be one of {self.VALID_DIRECTIONS}, got {self.direction!r}")
        return True

    def age_days(self, reference_time: datetime | None = None) -> int:
        """Days since the observation was made."""
        ref = reference_time or self.created_at
        return days_between(self.observation_timestamp, ref)

    def aging_multiplier(self, reference_time: datetime | None = None) -> float:
        """
        Compute the aging multiplier based on age.

        Fresh (0-7 days): 1.0
        Recent (8-30 days): 0.90
        Mature (31-90 days): 0.75
        Stale (91+ days): 0.50

        Args:
            reference_time: The time to use as "now" for age computation.
                            If None, uses the current system time (non-deterministic).
        """
        age = self.age_days(reference_time)
        if age <= AGING_FRESH_MAX_DAYS:
            return AGING_FRESH_MULTIPLIER
        elif age <= AGING_RECENT_MAX_DAYS:
            return AGING_RECENT_MULTIPLIER
        elif age <= AGING_MATURE_MAX_DAYS:
            return AGING_MATURE_MULTIPLIER
        else:
            return AGING_STALE_MULTIPLIER

    def weight(self, reference_time: datetime | None = None) -> float:
        """
        Compute the evidence weight.

        Weight = Confidence Ã— AgingMultiplier Ã— TierMultiplier

        Args:
            reference_time: The time to use as "now" for age computation.
                            If None, uses the current system time (non-deterministic).
        """
        tier_multiplier = {
            "Primary": TIER_PRIMARY_MULTIPLIER,
            "Secondary": TIER_SECONDARY_MULTIPLIER,
            "Tertiary": TIER_TERTIARY_MULTIPLIER,
        }.get(self.tier, TIER_PRIMARY_MULTIPLIER)

        return self.confidence * self.aging_multiplier(reference_time) * tier_multiplier

    def _to_hashable_dict(self) -> dict:
        return {
            "observation_id": self.observation_id,
            "hypothesis_id": self.hypothesis_id,
            "interpretation": self.interpretation,
            "direction": self.direction,
            "source_reliability": self.source_reliability,
            "recency": self.recency,
            "relevance": self.relevance,
            "consensus": self.consensus,
            "structural_importance": self.structural_importance,
            "quality_factor": self.quality_factor,
            "uncertainty": self.uncertainty,
            "tier": self.tier,
            "dependencies": sorted(self.dependencies),
            "conflicts": sorted(self.conflicts),
            "ontology_tags": sorted(self.ontology_tags),
        }

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update(
            {
                "observation_id": self.observation_id,
                "hypothesis_id": self.hypothesis_id,
                "interpretation": self.interpretation,
                "direction": self.direction,
                "quality": self.quality,
                "confidence": self.confidence,
                "weight": self.weight(self.created_at),
                "tier": self.tier,
                "age_days": self.age_days(self.created_at),
                "aging_multiplier": self.aging_multiplier(self.created_at),
                "observation_timestamp": format_timestamp(self.observation_timestamp),
                "dependencies": self.dependencies,
                "conflicts": self.conflicts,
                "source_reliability": self.source_reliability,
                "recency": self.recency,
                "relevance": self.relevance,
                "consensus": self.consensus,
                "structural_importance": self.structural_importance,
                "quality_factor": self.quality_factor,
                "uncertainty": self.uncertainty,
            }
        )
        return base

    @classmethod
    def from_dict(cls, data: dict) -> Evidence:
        obj = super().from_dict(data)
        obj.observation_id = data["observation_id"]
        obj.hypothesis_id = data["hypothesis_id"]
        obj.interpretation = data["interpretation"]
        obj.direction = data.get("direction", "Neutral")
        obj.source_reliability = data.get("source_reliability", 1.0)
        obj.recency = data.get("recency", 1.0)
        obj.relevance = data.get("relevance", 1.0)
        obj.consensus = data.get("consensus", 1.0)
        obj.structural_importance = data.get("structural_importance", 1.0)
        obj.quality_factor = data.get("quality_factor", 1.0)
        obj.uncertainty = data.get("uncertainty", 0.0)
        obj.tier = data.get("tier", "Primary")
        obj.observation_timestamp = parse_timestamp(data["observation_timestamp"]) if data.get("observation_timestamp") else None
        obj.dependencies = list(data.get("dependencies", []))
        obj.conflicts = list(data.get("conflicts", []))
        obj.quality = data.get("quality", obj._compute_quality())
        obj.confidence = data.get("confidence", obj._compute_confidence())
        return obj


class EvidenceRegistry(BaseObject):
    """
    A collection of all evidence for a research cycle.

    Based on Article XVII: Object Model â€” EvidenceRegistry.
    """

    def __init__(
        self,
        research_id: str,
        evidence: list[Evidence] | None = None,
        ontology_tags: list[str] | None = None,
        id: str | None = None,
    ):
        if id is None:
            seed = f"EvidenceRegistry|{research_id}"
            id = generate_id(seed)

        super().__init__(id=id, ontology_tags=ontology_tags)
        self.research_id = research_id
        self.evidence: list[Evidence] = evidence or []
        self._evidence_ids: list[str] = []

    def total_weight(self, reference_time: datetime | None = None) -> float:
        return sum(e.weight(reference_time) for e in self.evidence)

    def supporting_weight(self, reference_time: datetime | None = None) -> float:
        return sum(e.weight(reference_time) for e in self.evidence if e.direction == "Supporting")

    def contradicting_weight(self, reference_time: datetime | None = None) -> float:
        return sum(e.weight(reference_time) for e in self.evidence if e.direction == "Contradicting")

    def add_evidence(self, evidence: Evidence) -> None:
        """Add an evidence entry to the registry."""
        self.evidence.append(evidence)
        self._evidence_ids.append(evidence.id)

    def get_by_direction(self, direction: str) -> list[Evidence]:
        """Get all evidence with a specific direction."""
        return [e for e in self.evidence if e.direction == direction]

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update(
            {
                "research_id": self.research_id,
                "evidence_ids": self._get_evidence_ids(),
            }
        )
        return base

    def _get_evidence_ids(self) -> list[str]:
        return self._evidence_ids

    @classmethod
    def from_dict(cls, data: dict) -> EvidenceRegistry:
        obj = super().from_dict(data)
        obj.research_id = data["research_id"]
        obj.evidence = []
        obj._evidence_ids = list(data.get("evidence_ids", []))
        return obj

    @property
    def evidence_ids(self) -> list[str]:
        return self._get_evidence_ids()

    @evidence_ids.setter
    def evidence_ids(self, value: list[str]) -> None:
        self._evidence_ids = value

    def _to_hashable_dict(self) -> dict:
        return {
            "research_id": self.research_id,
            "evidence_ids": sorted(self.evidence_ids),
            "ontology_tags": sorted(self.ontology_tags),
        }
