"""
DecisionReport — the final explainable output of the decision pipeline.

Based on Article XVII: Object Model — Decision Engine Layer.

Purpose:
    DecisionReport is the complete output of the decision pipeline.
    It includes:
        - Decision summary (asset, timeframe, timestamp)
        - Probability table (bullish, bearish, neutral)
        - Supporting evidence references
        - Historical similar cases
        - Experiment references
        - Macro factors
        - Risk factors
        - Confidence
        - Limitations
        - Calculation version
        - Reasoning chain
        - Audit trail

    Every DecisionReport is:
        - Deterministic: Same inputs → same report
        - Auditable: Full lifecycle tracking
        - Versioned: Calculation versions for reproducibility
        - Self-contained: All context needed to understand the decision

Pipeline:
    DecisionContext → EvidenceAggregator → EvidenceScore →
    ProbabilityAssessment → DecisionReasoner → DecisionReport
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from researchos.core.base_object import BaseObject
from researchos.core.identity import deterministic_hash, generate_id
from researchos.core.lifecycle import LifecycleStage
from researchos.core.timestamp import parse_timestamp, utc_now
from researchos.decision_engine.context import DecisionContext
from researchos.decision_engine.contracts import (
    CalculationMethod,
    DecisionStatus,
    WeightConfiguration,
)
from researchos.decision_engine.probability import ProbabilityAssessment
from researchos.decision_engine.reasoner import DecisionReasoner, ReasoningStep
from researchos.decision_engine.score import EvidenceScore


class DecisionReport(BaseObject):
    """
    Complete explainable decision output.

    This is the final output of the decision pipeline. It is fully
    self-contained — anyone reading this report can understand:
        - What was decided
        - Why it was decided that way
        - What evidence supported it
        - What evidence contradicted it
        - What reduced confidence
        - Which historical scenarios contributed
        - Which experiments contributed
        - Which macro factors contributed

    Attributes:
        asset: Asset symbol.
        timeframe: Bar timeframe.
        decision_timestamp: When the decision was made.
        context_id: Link to DecisionContext.
        score_id: Link to EvidenceScore.
        probability_id: Link to ProbabilityAssessment.
        report_version: Version of report format.
        evidence_version: Version of evidence collection methodology.
        scoring_version: Version of scoring methodology.
        probability_version: Version of probability methodology.
        reasoner_version: Version of reasoning methodology.
        weight_config: Weight configuration used.
        bullish_probability: Final bullish probability.
        bearish_probability: Final bearish probability.
        neutral_probability: Final neutral probability.
        confidence: Overall confidence.
        uncertainty: Overall uncertainty.
        summary: Human-readable decision summary.
        reasoning_steps: Complete reasoning chain.
        evidence_summary: Summary of evidence collected.
        supporting_evidence: IDs of supporting evidence.
        historical_scenarios: IDs of historical scenarios used.
        experiment_ids: IDs of experiments used.
        macro_factors: Macro factors considered.
        risk_factors: Risk factors identified.
        limitations: Limitations of this decision.
        calculation_method: Method used.
        calculation_version: Version of calculation methodology.
        tags: Decision tags.
        report_hash: Deterministic hash of the report.
    """

    def __init__(
        self,
        asset: str,
        timeframe: str = "",
        decision_timestamp: datetime | None = None,
        context_id: str = "",
        score_id: str = "",
        probability_id: str = "",
        report_version: str = "REPORT_V1",
        evidence_version: str = "EVIDENCE_V1",
        scoring_version: str = "SCORE_V1",
        probability_version: str = "DECISION_V1",
        reasoner_version: str = "REASON_V1",
        weight_config: WeightConfiguration | None = None,
        bullish_probability: float = 0.33,
        bearish_probability: float = 0.33,
        neutral_probability: float = 0.34,
        confidence: float = 0.0,
        uncertainty: float = 1.0,
        summary: str = "",
        reasoning_steps: list[ReasoningStep] | None = None,
        evidence_summary: str = "",
        supporting_evidence: list[str] | None = None,
        historical_scenarios: list[str] | None = None,
        experiment_ids: list[str] | None = None,
        macro_factors: list[dict[str, Any]] | None = None,
        risk_factors: list[str] | None = None,
        limitations: list[str] | None = None,
        calculation_method: CalculationMethod = CalculationMethod.WEIGHTED_EVIDENCE,
        calculation_version: str = "DECISION_V1",
        tags: list[str] | None = None,
        ontology_tags: list[str] | None = None,
        id: str | None = None,
    ):
        if id is None:
            seed = f"DecisionReport|{asset}|{decision_timestamp.isoformat() if decision_timestamp else ''}"
            id = generate_id(seed)

        super().__init__(id=id, ontology_tags=ontology_tags)

        self.asset = asset
        self.timeframe = timeframe
        self.decision_timestamp = decision_timestamp or utc_now()
        self.context_id = context_id
        self.score_id = score_id
        self.probability_id = probability_id
        self.report_version = report_version
        self.evidence_version = evidence_version
        self.scoring_version = scoring_version
        self.probability_version = probability_version
        self.reasoner_version = reasoner_version
        self.weight_config = weight_config or WeightConfiguration()
        self.bullish_probability = bullish_probability
        self.bearish_probability = bearish_probability
        self.neutral_probability = neutral_probability
        self.confidence = confidence
        self.uncertainty = uncertainty
        self.summary = summary
        self.reasoning_steps: list[ReasoningStep] = reasoning_steps or []
        self.evidence_summary = evidence_summary
        self.supporting_evidence: list[str] = supporting_evidence or []
        self.historical_scenarios: list[str] = historical_scenarios or []
        self.experiment_ids: list[str] = experiment_ids or []
        self.macro_factors: list[dict[str, Any]] = macro_factors or []
        self.risk_factors: list[str] = risk_factors or []
        self.limitations: list[str] = limitations or []
        self.calculation_method = calculation_method
        self.calculation_version = calculation_version
        self.tags: list[str] = tags or []
        self.status = DecisionStatus.REPORT_GENERATED
        self._report_hash: str = ""

        self._update_hash()

        self.lifecycle.transition(
            LifecycleStage.COMPLETE,
            reason=f"Decision report generated for {asset}: B={bullish_probability:.2%}, Be={bearish_probability:.2%}, N={neutral_probability:.2%}",
        )

    @property
    def report_hash(self) -> str:
        """Get the deterministic hash of this report."""
        if not self._report_hash:
            self._update_hash()
        return self._report_hash

    def _update_hash(self) -> None:
        """Compute the deterministic hash."""
        content = self._to_hashable_dict()
        self._report_hash = deterministic_hash(content)

    def _to_hashable_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "timeframe": self.timeframe,
            "decision_timestamp": self.decision_timestamp.isoformat(),
            "context_id": self.context_id,
            "score_id": self.score_id,
            "probability_id": self.probability_id,
            "report_version": self.report_version,
            "evidence_version": self.evidence_version,
            "scoring_version": self.scoring_version,
            "probability_version": self.probability_version,
            "reasoner_version": self.reasoner_version,
            "weight_config": self.weight_config.to_dict(),
            "bullish_probability": self.bullish_probability,
            "bearish_probability": self.bearish_probability,
            "neutral_probability": self.neutral_probability,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "summary": self.summary,
            "reasoning_steps": [s.to_dict() for s in self.reasoning_steps],
            "evidence_summary": self.evidence_summary,
            "supporting_evidence": sorted(self.supporting_evidence),
            "historical_scenarios": sorted(self.historical_scenarios),
            "experiment_ids": sorted(self.experiment_ids),
            "macro_factors": self.macro_factors,
            "risk_factors": sorted(self.risk_factors),
            "limitations": sorted(self.limitations),
            "calculation_method": self.calculation_method.value,
            "calculation_version": self.calculation_version,
            "tags": sorted(self.tags),
            "ontology_tags": sorted(self.ontology_tags),
        }

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update(
            {
                "asset": self.asset,
                "timeframe": self.timeframe,
                "decision_timestamp": self.decision_timestamp.isoformat(),
                "context_id": self.context_id,
                "score_id": self.score_id,
                "probability_id": self.probability_id,
                "report_version": self.report_version,
                "evidence_version": self.evidence_version,
                "scoring_version": self.scoring_version,
                "probability_version": self.probability_version,
                "reasoner_version": self.reasoner_version,
                "weight_config": self.weight_config.to_dict(),
                "bullish_probability": self.bullish_probability,
                "bearish_probability": self.bearish_probability,
                "neutral_probability": self.neutral_probability,
                "confidence": self.confidence,
                "uncertainty": self.uncertainty,
                "summary": self.summary,
                "reasoning_steps": [s.to_dict() for s in self.reasoning_steps],
                "evidence_summary": self.evidence_summary,
                "supporting_evidence": self.supporting_evidence,
                "historical_scenarios": self.historical_scenarios,
                "experiment_ids": self.experiment_ids,
                "macro_factors": self.macro_factors,
                "risk_factors": self.risk_factors,
                "limitations": self.limitations,
                "calculation_method": self.calculation_method.value,
                "calculation_version": self.calculation_version,
                "status": self.status.value,
                "tags": self.tags,
                "report_hash": self._report_hash,
            }
        )
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionReport:
        obj = super().from_dict(data)
        obj.asset = data["asset"]
        obj.timeframe = data.get("timeframe", "")
        obj.decision_timestamp = parse_timestamp(data["decision_timestamp"])
        obj.context_id = data.get("context_id", "")
        obj.score_id = data.get("score_id", "")
        obj.probability_id = data.get("probability_id", "")
        obj.report_version = data.get("report_version", "REPORT_V1")
        obj.evidence_version = data.get("evidence_version", "EVIDENCE_V1")
        obj.scoring_version = data.get("scoring_version", "SCORE_V1")
        obj.probability_version = data.get("probability_version", "DECISION_V1")
        obj.reasoner_version = data.get("reasoner_version", "REASON_V1")
        obj.weight_config = WeightConfiguration.from_dict(data.get("weight_config", {}))
        obj.bullish_probability = float(data.get("bullish_probability", 0.33))
        obj.bearish_probability = float(data.get("bearish_probability", 0.33))
        obj.neutral_probability = float(data.get("neutral_probability", 0.34))
        obj.confidence = float(data.get("confidence", 0.0))
        obj.uncertainty = float(data.get("uncertainty", 1.0))
        obj.summary = data.get("summary", "")
        obj.reasoning_steps = [ReasoningStep(**s) for s in data.get("reasoning_steps", [])]
        obj.evidence_summary = data.get("evidence_summary", "")
        obj.supporting_evidence = list(data.get("supporting_evidence", []))
        obj.historical_scenarios = list(data.get("historical_scenarios", []))
        obj.experiment_ids = list(data.get("experiment_ids", []))
        obj.macro_factors = list(data.get("macro_factors", []))
        obj.risk_factors = list(data.get("risk_factors", []))
        obj.limitations = list(data.get("limitations", []))
        obj.calculation_method = CalculationMethod(data.get("calculation_method", "WeightedEvidence"))
        obj.calculation_version = data.get("calculation_version", "DECISION_V1")
        obj.status = DecisionStatus(data.get("status", "ReportGenerated"))
        obj.tags = list(data.get("tags", []))
        obj._report_hash = data.get("report_hash", "")
        return obj


def generate_decision_report(
    context: DecisionContext,
    score: EvidenceScore,
    probability: ProbabilityAssessment,
    reasoner: DecisionReasoner | None = None,
) -> DecisionReport:
    """
    Generate a complete DecisionReport from pipeline outputs.

    This is the top-level function that:
        1. Runs the reasoner to produce a reasoning chain
        2. Gathers supporting evidence references
        3. Identifies macro factors and risk factors
        4. Creates the self-contained DecisionReport

    Args:
        context: Original decision context.
        score: Computed evidence score.
        probability: Computed probability assessment.
        reasoner: Optional custom reasoner (uses default if not provided).

    Returns:
        Fully populated DecisionReport.
    """
    if reasoner is None:
        reasoner = DecisionReasoner()

    reasoning_steps = reasoner.reason(context, score, probability)

    # Gather supporting evidence (sorted for deterministic report content)
    supporting_ids = sorted({item.source_id for item in score.evidence_items if item.source_id})

    # Gather historical scenarios
    historical_ids = sorted(set(context.historical_scenario_ids))

    # Gather experiment IDs
    experiment_ids = list(context.experiment_result_ids)

    # Macro factors — DecisionContext carries only object references, so the
    # report lists which canonical macro references were considered.
    macro_factors = []
    if context.macro_state_id:
        macro_factors.append(
            {
                "indicator": "macro_state_id",
                "value": context.macro_state_id,
                "impact": "considered",
            }
        )
    if context.market_regime_id:
        macro_factors.append(
            {
                "indicator": "market_regime_id",
                "value": context.market_regime_id,
                "impact": "considered",
            }
        )

    # Risk factors
    risk_factors = []
    if score.uncertainty_score > 0.5:
        risk_factors.append(f"High source disagreement (uncertainty={score.uncertainty_score:.2f})")
    if score.confidence_score < 0.3:
        risk_factors.append(f"Low evidence confidence (confidence={score.confidence_score:.2f})")
    if len(score.evidence_items) < 3:
        risk_factors.append(f"Insufficient evidence volume ({len(score.evidence_items)} items)")
    if not context.historical_scenario_ids:
        risk_factors.append("No historical scenario matches available")

    # Evidence summary
    source_counts: dict[str, int] = {}
    for item in score.evidence_items:
        src = item.source.value
        source_counts[src] = source_counts.get(src, 0) + 1
    evidence_summary = f"Total evidence: {score.evidence_count} items from {len(source_counts)} sources. " + ", ".join(f"{k}: {v}" for k, v in sorted(source_counts.items()))

    # Human-readable summary
    directional_label = "Bullish" if probability.bullish_probability > probability.bearish_probability else "Bearish" if probability.bearish_probability > probability.bullish_probability else "Neutral"
    summary = f"{directional_label} bias for {context.asset} ({context.timeframe}) with {probability.confidence:.0%} confidence. Bullish={probability.bullish_probability:.1%}, Bearish={probability.bearish_probability:.1%}, Neutral={probability.neutral_probability:.1%}. Based on {len(reasoning_steps)} reasoning steps, {score.evidence_count} evidence items, {len(context.historical_scenario_ids)} historical matches."

    return DecisionReport(
        asset=context.asset,
        timeframe=context.timeframe,
        decision_timestamp=context.decision_timestamp,
        context_id=context.id,
        score_id=score.id,
        probability_id=probability.id,
        scoring_version=score.scoring_version,
        probability_version=probability.calculation_version,
        reasoner_version=reasoner.reasoning_version,
        bullish_probability=probability.bullish_probability,
        bearish_probability=probability.bearish_probability,
        neutral_probability=probability.neutral_probability,
        confidence=probability.confidence,
        uncertainty=probability.uncertainty,
        summary=summary,
        reasoning_steps=reasoning_steps,
        evidence_summary=evidence_summary,
        supporting_evidence=supporting_ids,
        historical_scenarios=historical_ids,
        experiment_ids=experiment_ids,
        macro_factors=macro_factors,
        risk_factors=risk_factors,
        limitations=probability.limitations,
        calculation_method=probability.calculation_method,
        calculation_version=probability.calculation_version,
        tags=context.ontology_tags,
        ontology_tags=["decision_engine", "decision_report"],
    )
