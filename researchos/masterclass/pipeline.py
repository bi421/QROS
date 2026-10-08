"""MASTERCLASS evidence -> probability -> risk handoff.

This layer deliberately does not place orders. It produces an explainable,
hash-linked assessment that can be converted into canonical DecisionEvidenceItem
objects and then passed to the existing governed decision/risk pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from researchos.decision_engine.contracts import (
    DecisionEvidenceItem,
    EvidenceSource,
    ProbabilityOutcome,
)
from .contracts import EvidenceBundle, EconomicObservation


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _direction(value: float) -> str:
    if value > 0.0:
        return "bullish"
    if value < 0.0:
        return "bearish"
    return "neutral"


@dataclass(frozen=True)
class MasterclassAssessment:
    """Six-branch assessment with explicit limitations and no hidden certainty."""

    what_happened: str
    why_it_happened: str
    current_conditions: str
    historical_context: str
    bullish_probability: float
    bearish_probability: float
    neutral_probability: float
    expected_r: float | None
    risk_fraction: float | None
    decision: str
    evidence_hash: str
    limitations: tuple[str, ...] = ()

    def validate(self) -> None:
        probabilities = (
            self.bullish_probability,
            self.bearish_probability,
            self.neutral_probability,
        )
        if any(not math.isfinite(p) or p < 0 or p > 1 for p in probabilities):
            raise ValueError("probabilities must be finite and in [0, 1]")
        if abs(sum(probabilities) - 1.0) > 1e-9:
            raise ValueError("probabilities must sum to 1")
        if self.expected_r is not None and not math.isfinite(self.expected_r):
            raise ValueError("expected_r must be finite")
        if self.risk_fraction is not None and not 0 <= self.risk_fraction <= 1:
            raise ValueError("risk_fraction must be in [0, 1]")


class MasterclassPipeline:
    """Deterministic first-pass fusion of the six MASTERCLASS branches."""

    VERSION = "MASTERCLASS_V1"

    def build(self, evidence: EvidenceBundle) -> MasterclassAssessment:
        evidence.validate()
        macro_score = self._macro_score(evidence.macro)
        relationship_score = self._relationship_score(evidence.relationships)
        technical_score = self._technical_score(evidence.technical)
        psychology_penalty = self._psychology_penalty(evidence.psychology)
        human_penalty = self._human_penalty(evidence.human)

        base = (
            0.35 * macro_score
            + 0.25 * relationship_score
            + 0.40 * technical_score
        )
        base -= psychology_penalty + human_penalty
        base = max(-1.0, min(1.0, base))

        historical = evidence.historical
        if historical is not None and historical.sample_size > 0:
            hp = historical.bullish_probability
            historical_score = 2.0 * hp - 1.0
            base = 0.75 * base + 0.25 * historical_score

        bullish = _clamp(0.5 + 0.5 * base)
        bearish = _clamp(0.5 - 0.5 * base)
        neutral = max(0.0, 1.0 - bullish - bearish)
        # Convert the signed score to a valid three-way distribution.
        bullish, bearish = bullish * 0.9, bearish * 0.9
        neutral = 1.0 - bullish - bearish

        expected_r = None
        if historical is not None and historical.sample_size > 0:
            b = max(0.0, historical.bullish_probability)
            expected_r = b * 1.0 - (1.0 - b) * 1.0

        risk_fraction = None
        if evidence.human is not None:
            risk_fraction = max(0.0, 0.01 * (1.0 - human_penalty * 10.0))
        if psychology_penalty > 0.0:
            risk_fraction = min(
                0.01 if risk_fraction is None else risk_fraction,
                0.01 * max(0.0, 1.0 - psychology_penalty * 10.0),
            )

        limitations: list[str] = []
        if not evidence.macro:
            limitations.append("No macro observations supplied")
        if not evidence.relationships:
            limitations.append("No cross-asset relationships supplied")
        if not evidence.technical:
            limitations.append("No technical/microstructure evidence supplied")
        if historical is None:
            limitations.append("No historical conditional outcome supplied")
        if evidence.human is None:
            limitations.append("Human state not supplied; no human-risk adjustment")
        if not evidence.psychology:
            limitations.append("No behavioral evidence supplied")
        if expected_r is None:
            limitations.append("Expected R is unavailable without historical outcome/payoff data")

        dominant = "BULLISH" if bullish > bearish else "BEARISH" if bearish > bullish else "NEUTRAL"
        decision = "REVIEW" if max(bullish, bearish) < 0.60 else dominant

        assessment = MasterclassAssessment(
            what_happened=self._what_happened(evidence.macro),
            why_it_happened=self._why(evidence),
            current_conditions=(
                f"macro={macro_score:+.3f}; relationship={relationship_score:+.3f}; "
                f"technical={technical_score:+.3f}; human_penalty={human_penalty:.3f}; "
                f"psychology_penalty={psychology_penalty:.3f}"
            ),
            historical_context=(
                "none"
                if historical is None
                else f"n={historical.sample_size}; "
                     f"p_bullish={historical.bullish_probability:.4f}; "
                     f"p_bearish={historical.bearish_probability:.4f}"
            ),
            bullish_probability=bullish,
            bearish_probability=bearish,
            neutral_probability=neutral,
            expected_r=expected_r,
            risk_fraction=risk_fraction,
            decision=decision,
            evidence_hash=evidence.content_hash(),
            limitations=tuple(limitations),
        )
        assessment.validate()
        return assessment

    @staticmethod
    def _macro_score(items: tuple[EconomicObservation, ...]) -> float:
        if not items:
            return 0.0
        # The sign is deliberately generic. Domain-specific interpretation belongs
        # in a versioned mapping rather than being silently assumed here.
        scores = [_clamp(abs(x.surprise) / (abs(x.expected) + 1e-9)) *
                  x.surprise_direction for x in items if x.surprise is not None]
        return sum(scores) / len(scores) if scores else 0.0

    @staticmethod
    def _relationship_score(items: tuple[Any, ...]) -> float:
        if not items:
            return 0.0
        scores = []
        for item in items:
            sign = 1.0 if item.direction.lower() == "bullish" else -1.0 if item.direction.lower() == "bearish" else 0.0
            scores.append(item.correlation * sign)
        return sum(scores) / len(scores)

    @staticmethod
    def _technical_score(items: tuple[Any, ...]) -> float:
        if not items:
            return 0.0
        return sum(
            (1.0 if x.direction.lower() == "bullish" else -1.0 if x.direction.lower() == "bearish" else 0.0)
            * x.strength * x.confidence
            for x in items
        ) / len(items)

    @staticmethod
    def _psychology_penalty(items: tuple[Any, ...]) -> float:
        return min(0.5, sum(x.strength * x.confidence for x in items) / max(1, len(items)) * 0.5)

    @staticmethod
    def _human_penalty(item: Any) -> float:
        if item is None:
            return 0.0
        stress = item.stress if item.stress is not None else 0.0
        fatigue = item.fatigue if item.fatigue is not None else 0.0
        attention = item.attention if item.attention is not None else 1.0
        return min(0.5, 0.25 * stress + 0.25 * fatigue + 0.25 * (1.0 - attention))

    @staticmethod
    def _what_happened(items: tuple[EconomicObservation, ...]) -> str:
        if not items:
            return "No external macro event supplied."
        parts = []
        for item in items:
            if item.surprise is None:
                parts.append(f"{item.name}: actual={item.actual}")
            else:
                parts.append(f"{item.name}: actual={item.actual}, expected={item.expected}, surprise={item.surprise:+g}")
        return "; ".join(parts)

    @staticmethod
    def _why(evidence: EvidenceBundle) -> str:
        causes = []
        if evidence.macro:
            causes.append("macro surprise")
        if evidence.relationships:
            causes.append("cross-asset relationship")
        if evidence.technical:
            causes.append("technical/microstructure evidence")
        if evidence.historical is not None:
            causes.append("historical conditional outcome")
        return " + ".join(causes) if causes else "Insufficient evidence to explain movement."

    def to_decision_evidence(self, assessment: MasterclassAssessment) -> list[DecisionEvidenceItem]:
        """Convert the assessment into canonical DecisionEngine evidence items."""
        assessment.validate()
        items: list[DecisionEvidenceItem] = []
        if assessment.bullish_probability >= assessment.bearish_probability:
            outcome = ProbabilityOutcome.BULLISH
            strength = assessment.bullish_probability
        else:
            outcome = ProbabilityOutcome.BEARISH
            strength = assessment.bearish_probability
        items.append(
            DecisionEvidenceItem(
                source=EvidenceSource.QUANT_ENGINE,
                source_id=f"masterclass:{assessment.evidence_hash}",
                direction=outcome,
                strength=strength,
                weight=1.0,
                confidence=max(assessment.bullish_probability, assessment.bearish_probability),
                description=assessment.why_it_happened,
                provenance={
                    "masterclass_version": self.VERSION,
                    "evidence_hash": assessment.evidence_hash,
                    "limitations": list(assessment.limitations),
                },
            )
        )
        return items
