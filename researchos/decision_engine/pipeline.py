"""End-to-end Decision Intelligence Engine pipeline.

Composition:
    DecisionContext -> EvidenceAggregator -> EvidenceScore ->
    ProbabilityAssessment -> DecisionReasoner -> DecisionReport

The pipeline owns orchestration only. Scientific calculations remain in their
existing modules. Validation is fail-closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from researchos.orchestration.parallel import ParallelResearchExecutor, ResearchBranch, ResearchWave
from researchos.decision_engine.calibration import CalibrationEvidence
from researchos.decision_engine.context import DecisionContext, DecisionContextValidator
from researchos.decision_engine.contracts import WeightConfiguration
from researchos.decision_engine.evidence import EvidenceAggregator, EvidenceCollection, EvidenceValidator
from researchos.decision_engine.probability import ProbabilityAssessment, ProbabilityCalculator, ProbabilityValidator
from researchos.decision_engine.reasoner import DecisionReasoner
from researchos.decision_engine.report import DecisionReport, generate_decision_report
from researchos.decision_engine.score import EvidenceScore, compute_evidence_score


class DecisionPipelineError(ValueError):
    """Raised when a decision pipeline stage violates its contract."""


@dataclass(frozen=True)
class DecisionPipelineResult:
    """Complete auditable output, including every intermediate artifact."""

    context: DecisionContext
    evidence: EvidenceCollection
    score: EvidenceScore
    probability: ProbabilityAssessment
    report: DecisionReport

    @property
    def report_hash(self) -> str:
        return self.report.report_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context.to_dict(),
            "evidence": self.evidence.to_dict(),
            "score": self.score.to_dict(),
            "probability": self.probability.to_dict(),
            "report": self.report.to_dict(),
        }


class DecisionPipeline:
    """Compose the decision-engine stages without duplicating their logic."""

    def __init__(
        self,
        *,
        aggregator: EvidenceAggregator | None = None,
        weight_config: WeightConfiguration | None = None,
        probability_calculator: ProbabilityCalculator | None = None,
        reasoner: DecisionReasoner | None = None,
        calibration_evidence: CalibrationEvidence | None = None,
    ) -> None:
        self.aggregator = aggregator or EvidenceAggregator()
        self.weight_config = weight_config or WeightConfiguration()
        self.probability_calculator = probability_calculator or ProbabilityCalculator()
        self.reasoner = reasoner or DecisionReasoner()
        if calibration_evidence is not None:
            calibration_evidence.validate()
        self.calibration_evidence = calibration_evidence
        self.context_validator = DecisionContextValidator()
        self.evidence_validator = EvidenceValidator()
        self.probability_validator = ProbabilityValidator()

    @staticmethod
    def _raise_if_errors(stage: str, errors: list[str]) -> None:
        if errors:
            raise DecisionPipelineError(f"{stage} validation failed: {'; '.join(errors)}")

    def run_many(
        self,
        contexts: tuple[DecisionContext, ...],
        *,
        executor: ParallelResearchExecutor | None = None,
    ) -> tuple[DecisionPipelineResult, ...]:
        """Evaluate independent decision contexts concurrently in declared order."""
        if not contexts:
            raise DecisionPipelineError("at least one DecisionContext is required")
        branch = tuple(
            ResearchBranch(
                branch_id=f"{context.id}:{index}",
                run=lambda _snapshot, context=context: self.run(context),
            )
            for index, context in enumerate(contexts)
        )
        plan = (ResearchWave(wave_id="decision-contexts", branches=branch),)
        result = (executor or ParallelResearchExecutor(max_workers=min(8, len(contexts)))).run(plan)
        return tuple(item.value for item in result.waves[0])

    def run(self, context: DecisionContext) -> DecisionPipelineResult:
        """Run every decision stage in dependency order, fail-closed."""
        self._raise_if_errors("DecisionContext", self.context_validator.validate(context))

        evidence = self.aggregator.aggregate(context)
        self._raise_if_errors("EvidenceCollection", self.evidence_validator.validate_collection(evidence))

        score = compute_evidence_score(context.id, evidence.items, self.weight_config)

        probability = self.probability_calculator.calculate(evidence)
        if self.calibration_evidence is not None:
            probability = probability.with_calibration_status(self.calibration_evidence.status.value)
        self._raise_if_errors("ProbabilityAssessment", self.probability_validator.validate(probability))

        report = generate_decision_report(context, score, probability, reasoner=self.reasoner)
        return DecisionPipelineResult(
            context=context,
            evidence=evidence,
            score=score,
            probability=probability,
            report=report,
        )


__all__ = ["DecisionPipeline", "DecisionPipelineError", "DecisionPipelineResult"]
