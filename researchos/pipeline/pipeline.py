"""
ResearchPipeline — minimal coordinator for the research object lifecycle.

This pipeline connects existing object models into a deterministic sequence
without introducing new intelligence, trading logic, or decision engines.

Every pipeline method:
    1. Validates input references via ReferenceValidator
    2. Creates the object deterministically (same inputs → same object)
    3. Links the object to its parent (updates parent ID lists)
    4. Saves all modified objects to the repository
    5. Creates an immutable AuditEntry for the transition
    6. Returns the newly created object

The pipeline NEVER:
    - Generates market predictions or conclusions
    - Selects, ranks, or filters hypotheses/scenarios
    - Computes trading signals or recommendations
    - Makes cognitive assessments of the trader
"""

from datetime import datetime
from typing import Any, TypeVar

from researchos.objects.cognitive import CognitiveAssessment
from researchos.objects.confidence import Confidence, ConfidenceReport
from researchos.objects.contradiction import Contradiction, ContradictionReport
from researchos.objects.evidence import Evidence, EvidenceRegistry
from researchos.objects.hypothesis import Hypothesis, HypothesisSet
from researchos.objects.interpretation import Interpretation, Narrative
from researchos.objects.knowledge import Knowledge, Lesson
from researchos.objects.observation import Observation
from researchos.objects.process import AuditEntry, ReasoningChain, ResearchCycle
from researchos.objects.research import Research, ResearchReport
from researchos.objects.scenario import Scenario, ScenarioSet
from researchos.objects.validation import FailureAnalysis, Validation
from researchos.pipeline.references import ReferenceValidator
from researchos.repository.interface import RepositoryInterface

T = TypeVar("T")


class ResearchPipeline:
    """
    Minimal coordinator for the research object lifecycle.

    Usage:
        pipeline = ResearchPipeline(repository)
        research = pipeline.start_research("What is inflation?")
        obs = pipeline.add_observation(research.id, "MACRO:CPI", ts, 3.2)
    """

    def __init__(self, repository: RepositoryInterface):
        """
        Initialize the pipeline with a repository for object storage.

        Args:
            repository: A RepositoryInterface implementation for
                        storing, retrieving, and validating objects.
        """
        self.repo = repository
        self.validator = ReferenceValidator(repository)

    def _require(self, object_id: str | None, cls: type[T]) -> T:
        """Load a repository object and enforce its concrete runtime type."""
        if object_id is None:
            raise ValueError(f"Missing required {cls.__name__} reference")
        obj = self.repo.get(object_id)
        if not isinstance(obj, cls):
            raise ValueError(f"Expected {cls.__name__} for '{object_id}'")
        return obj

    # ------------------------------------------------------------------
    # Stage 1: Research initiation
    # ------------------------------------------------------------------

    def start_research(
        self,
        question: str,
        time_horizon: str = "Daily",
        asset: str = "",
        methodology_version: str = "1.0.0",
        ontology_tags: list[str] | None = None,
    ) -> Research:
        """
        Start a new research cycle.

        This is the pipeline entry point. Creates a Research object
        and an initial ResearchCycle tracking record.
        """
        research = Research(
            question=question,
            time_horizon=time_horizon,
            asset=asset,
            methodology_version=methodology_version,
            ontology_tags=ontology_tags,
        )

        self.repo.save(research)

        cycle = ResearchCycle(research_id=research.id)
        self.repo.save(cycle)

        audit = AuditEntry(
            actor="pipeline",
            action="RESEARCH_STARTED",
            object_id=research.id,
            object_type="Research",
            before_state="",
            after_state=research.to_json(),
        )
        self.repo.save(audit)

        cycle.add_stage("start_research", 0.0, "Complete", {"research_id": research.id})
        self.repo.save(cycle)

        return research

    # ------------------------------------------------------------------
    # Stage 2: Observation → Evidence
    # ------------------------------------------------------------------

    def add_observation(
        self,
        research_id: str,
        source: str,
        timestamp: datetime,
        value: Any,
        unit: str = "",
        frequency: str = "",
        geography: str = "",
        asset_class: str = "",
        quality_flags: list[str] | None = None,
        retrieval_method: str = "",
        ontology_tags: list[str] | None = None,
    ) -> Observation:
        """
        Create an observation and link it to a research cycle.
        """
        self.validator.require_exists(research_id, "Research")

        obs = Observation(
            source=source,
            timestamp=timestamp,
            value=value,
            unit=unit,
            frequency=frequency,
            geography=geography,
            asset_class=asset_class,
            quality_flags=quality_flags,
            retrieval_time=timestamp,
            retrieval_method=retrieval_method,
            ontology_tags=ontology_tags,
        )

        self.repo.save(obs)

        research = self._require(research_id, Research)
        research.observation_ids.append(obs.id)
        self.repo.save(research)

        audit = AuditEntry(
            actor="pipeline",
            action="OBSERVATION_ADDED",
            object_id=obs.id,
            object_type="Observation",
            before_state="",
            after_state=obs.to_json(),
        )
        self.repo.save(audit)

        return obs

    def create_evidence(
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
        research_id: str | None = None,
    ) -> Evidence:
        """
        Create evidence from an observation, linked to a hypothesis.
        """
        self.validator.require_exists(observation_id, "Observation")
        self.validator.require_exists(hypothesis_id, "Hypothesis")

        ev = Evidence(
            observation_id=observation_id,
            hypothesis_id=hypothesis_id,
            interpretation=interpretation,
            direction=direction,
            source_reliability=source_reliability,
            recency=recency,
            relevance=relevance,
            consensus=consensus,
            structural_importance=structural_importance,
            quality_factor=quality_factor,
            uncertainty=uncertainty,
            tier=tier,
            observation_timestamp=observation_timestamp,
            dependencies=dependencies,
            conflicts=conflicts,
            ontology_tags=ontology_tags,
        )

        self.repo.save(ev)

        if research_id:
            self.validator.require_exists(research_id, "Research")
            research = self.repo.get(research_id)
            if not research.evidence_registry_id:
                registry = EvidenceRegistry(research_id=research_id)
                self.repo.save(registry)
                research.evidence_registry_id = registry.id
            else:
                registry = self._require(research.evidence_registry_id, EvidenceRegistry)
            registry.add_evidence(ev)
            self.repo.save(registry)
            self.repo.save(research)

        audit = AuditEntry(
            actor="pipeline",
            action="EVIDENCE_CREATED",
            object_id=ev.id,
            object_type="Evidence",
            before_state="",
            after_state=ev.to_json(),
        )
        self.repo.save(audit)

        return ev

    # ------------------------------------------------------------------
    # Stage 3: Interpretation
    # ------------------------------------------------------------------

    def create_interpretation(
        self,
        evidence_ids: list[str],
        rule_applied: str,
        context: str,
        conclusion: str,
        confidence: float = 0.0,
        supporting_evidence: list[str] | None = None,
        contradicting_evidence: list[str] | None = None,
        alternatives: list[str] | None = None,
        unknowns: list[str] | None = None,
        ontology_tags: list[str] | None = None,
    ) -> Interpretation:
        """
        Create an interpretation from evidence.
        """
        self.validator.require_all_exist(evidence_ids, "Evidence")

        interpretation = Interpretation(
            evidence_ids=evidence_ids,
            rule_applied=rule_applied,
            context=context,
            conclusion=conclusion,
            confidence=confidence,
            supporting_evidence=supporting_evidence,
            contradicting_evidence=contradicting_evidence,
            alternatives=alternatives,
            unknowns=unknowns,
            ontology_tags=ontology_tags,
        )

        self.repo.save(interpretation)

        audit = AuditEntry(
            actor="pipeline",
            action="INTERPRETATION_CREATED",
            object_id=interpretation.id,
            object_type="Interpretation",
            before_state="",
            after_state=interpretation.to_json(),
        )
        self.repo.save(audit)

        return interpretation

    def create_narrative(
        self,
        research_id: str,
        thesis: str,
        primary_driver: str = "",
        supporting_drivers: list[str] | None = None,
        interpretations: list[str] | None = None,
        evidence_strength: float = 0.0,
        coherence_score: float = 0.0,
        plausibility_score: float = 0.0,
        invalidation_conditions: list[str] | None = None,
        catalysts: list[str] | None = None,
        confidence: float = 0.0,
        ontology_tags: list[str] | None = None,
    ) -> Narrative:
        """
        Create a narrative linking interpretations together.
        """
        self.validator.require_exists(research_id, "Research")

        narrative = Narrative(
            research_id=research_id,
            thesis=thesis,
            primary_driver=primary_driver,
            supporting_drivers=supporting_drivers,
            interpretations=interpretations,
            evidence_strength=evidence_strength,
            coherence_score=coherence_score,
            plausibility_score=plausibility_score,
            invalidation_conditions=invalidation_conditions,
            catalysts=catalysts,
            confidence=confidence,
            ontology_tags=ontology_tags,
        )

        self.repo.save(narrative)

        audit = AuditEntry(
            actor="pipeline",
            action="NARRATIVE_CREATED",
            object_id=narrative.id,
            object_type="Narrative",
            before_state="",
            after_state=narrative.to_json(),
        )
        self.repo.save(audit)

        return narrative

    # ------------------------------------------------------------------
    # Stage 4: Hypothesis
    # ------------------------------------------------------------------

    def create_hypothesis(
        self,
        research_id: str,
        type: str,
        statement: str,
        narrative_id: str = "",
        evidence_ids: list[str] | None = None,
        evidence_strength: float = 0.0,
        coherence: float = 0.0,
        plausibility: float = 0.0,
        falsifiability: float = 0.0,
        confidence: float = 0.0,
        valid_if: list[str] | None = None,
        invalid_if: list[str] | None = None,
        monitoring_conditions: list[str] | None = None,
        ontology_tags: list[str] | None = None,
    ) -> Hypothesis:
        """
        Create a hypothesis within a research cycle.
        """
        self.validator.require_exists(research_id, "Research")
        if narrative_id:
            self.validator.require_exists(narrative_id, "Narrative")

        hypothesis = Hypothesis(
            research_id=research_id,
            type=type,
            statement=statement,
            narrative_id=narrative_id,
            evidence_ids=evidence_ids,
            evidence_strength=evidence_strength,
            coherence=coherence,
            plausibility=plausibility,
            falsifiability=falsifiability,
            confidence=confidence,
            valid_if=valid_if,
            invalid_if=invalid_if,
            monitoring_conditions=monitoring_conditions,
            ontology_tags=ontology_tags,
        )

        self.repo.save(hypothesis)

        research = self.repo.get(research_id)
        if not research.hypothesis_set_id:
            hs = HypothesisSet(research_id=research_id)
            self.repo.save(hs)
            research.hypothesis_set_id = hs.id
        else:
            hs = self._require(research.hypothesis_set_id, HypothesisSet)
        hs.add_hypothesis(hypothesis)
        self.repo.save(hs)
        self.repo.save(research)

        audit = AuditEntry(
            actor="pipeline",
            action="HYPOTHESIS_CREATED",
            object_id=hypothesis.id,
            object_type="Hypothesis",
            before_state="",
            after_state=hypothesis.to_json(),
        )
        self.repo.save(audit)

        return hypothesis

    # ------------------------------------------------------------------
    # Stage 5: Scenario
    # ------------------------------------------------------------------

    def create_scenario(
        self,
        research_id: str,
        hypothesis_id: str,
        type: str = "Base",
        label: str = "Scenario A",
        thesis: str = "",
        probability: float = 0.0,
        calibrated_probability: float | None = None,
        confidence_interval: dict | None = None,
        expected_return: float = 0.0,
        return_range: dict | None = None,
        volatility: float = 0.0,
        regime: str = "",
        assumptions: list[str] | None = None,
        dependencies: list[str] | None = None,
        valid_if: list[str] | None = None,
        invalid_if: list[str] | None = None,
        supporting_evidence: list[str] | None = None,
        contradicting_evidence: list[str] | None = None,
        milestones: list[str] | None = None,
        construction_trace: str = "",
        ontology_tags: list[str] | None = None,
    ) -> Scenario:
        """
        Create a scenario from a hypothesis.
        """
        self.validator.require_exists(research_id, "Research")
        self.validator.require_exists(hypothesis_id, "Hypothesis")

        scenario = Scenario(
            hypothesis_id=hypothesis_id,
            type=type,
            label=label,
            thesis=thesis,
            probability=probability,
            calibrated_probability=calibrated_probability,
            confidence_interval=confidence_interval,
            expected_return=expected_return,
            return_range=return_range,
            volatility=volatility,
            regime=regime,
            assumptions=assumptions,
            dependencies=dependencies,
            valid_if=valid_if,
            invalid_if=invalid_if,
            supporting_evidence=supporting_evidence,
            contradicting_evidence=contradicting_evidence,
            milestones=milestones,
            construction_trace=construction_trace,
            ontology_tags=ontology_tags,
        )

        self.repo.save(scenario)

        research = self.repo.get(research_id)
        if not research.scenario_set_id:
            ss = ScenarioSet(research_id=research_id)
            self.repo.save(ss)
            research.scenario_set_id = ss.id
        else:
            ss = self._require(research.scenario_set_id, ScenarioSet)
        ss.add_scenario(scenario)
        self.repo.save(ss)
        self.repo.save(research)

        audit = AuditEntry(
            actor="pipeline",
            action="SCENARIO_CREATED",
            object_id=scenario.id,
            object_type="Scenario",
            before_state="",
            after_state=scenario.to_json(),
        )
        self.repo.save(audit)

        return scenario

    # ------------------------------------------------------------------
    # Stage 6: Confidence
    # ------------------------------------------------------------------

    def register_confidence(
        self,
        target_id: str,
        target_type: str,
        evidence_strength: float = 0.0,
        coherence: float = 0.0,
        historical_precedent: float = 0.0,
        model_uncertainty: float = 0.0,
        recency: float = 0.0,
        penalties: list[str] | None = None,
        boosters: list[str] | None = None,
        ontology_tags: list[str] | None = None,
        research_id: str | None = None,
    ) -> Confidence:
        """
        Register a confidence estimate for a target object.
        """
        self.validator.require_exists(target_id, target_type)

        confidence = Confidence(
            target_id=target_id,
            target_type=target_type,
            evidence_strength=evidence_strength,
            coherence=coherence,
            historical_precedent=historical_precedent,
            model_uncertainty=model_uncertainty,
            recency=recency,
            penalties=penalties,
            boosters=boosters,
            ontology_tags=ontology_tags,
        )

        self.repo.save(confidence)

        if research_id:
            self.validator.require_exists(research_id, "Research")
            research = self.repo.get(research_id)
            if not research.confidence_report_id:
                cr = ConfidenceReport(research_id=research_id)
                self.repo.save(cr)
                research.confidence_report_id = cr.id
            else:
                cr = self._require(research.confidence_report_id, ConfidenceReport)
            cr.add_confidence(confidence)
            self.repo.save(cr)
            self.repo.save(research)

        audit = AuditEntry(
            actor="pipeline",
            action="CONFIDENCE_REGISTERED",
            object_id=confidence.id,
            object_type="Confidence",
            before_state="",
            after_state=confidence.to_json(),
        )
        self.repo.save(audit)

        return confidence

    # ------------------------------------------------------------------
    # Stage 7: Contradiction
    # ------------------------------------------------------------------

    def detect_contradiction(
        self,
        research_id: str,
        type: str,
        description: str,
        sides: list[dict] | None = None,
        ontology_tags: list[str] | None = None,
    ) -> Contradiction:
        """
        Record a contradiction within a research cycle.
        """
        self.validator.require_exists(research_id, "Research")

        for side in sides or []:
            for ev_id in side.get("evidence", []):
                self.validator.require_exists(ev_id, "Evidence")

        contradiction = Contradiction(
            research_id=research_id,
            type=type,
            description=description,
            sides=sides,
            ontology_tags=ontology_tags,
        )

        self.repo.save(contradiction)

        research = self.repo.get(research_id)
        if not research.contradiction_report_id:
            cr = ContradictionReport(research_id=research_id)
            self.repo.save(cr)
            research.contradiction_report_id = cr.id
        else:
            cr = self._require(research.contradiction_report_id, ContradictionReport)
        cr.add_contradiction(contradiction)
        self.repo.save(cr)
        self.repo.save(research)

        audit = AuditEntry(
            actor="pipeline",
            action="CONTRADICTION_DETECTED",
            object_id=contradiction.id,
            object_type="Contradiction",
            before_state="",
            after_state=contradiction.to_json(),
        )
        self.repo.save(audit)

        return contradiction

    # ------------------------------------------------------------------
    # Stage 8: Research Report
    # ------------------------------------------------------------------

    def generate_report(
        self,
        research_id: str,
        title: str = "",
        executive_summary: str = "",
        research_question: str = "",
        hypotheses: str = "",
        evidence_summary: str = "",
        analyses: str = "",
        narrative: str = "",
        scenarios: str = "",
        confidence: str = "",
        contradictions: str = "",
        risk_factors: list[str] | None = None,
        invalidation_conditions: list[str] | None = None,
        known_unknowns: list[str] | None = None,
        open_questions: list[str] | None = None,
        methodology_version: str = "1.0.0",
        format: str = "Markdown",
        ontology_tags: list[str] | None = None,
    ) -> ResearchReport:
        """
        Generate a research report from completed research.
        """
        self.validator.require_exists(research_id, "Research")

        report = ResearchReport(
            research_id=research_id,
            title=title,
            executive_summary=executive_summary,
            research_question=research_question,
            hypotheses=hypotheses,
            evidence_summary=evidence_summary,
            analyses=analyses,
            narrative=narrative,
            scenarios=scenarios,
            confidence=confidence,
            contradictions=contradictions,
            risk_factors=risk_factors,
            invalidation_conditions=invalidation_conditions,
            known_unknowns=known_unknowns,
            open_questions=open_questions,
            methodology_version=methodology_version,
            format=format,
            ontology_tags=ontology_tags,
        )

        self.repo.save(report)

        research = self.repo.get(research_id)
        research.report_id = report.id
        research.complete()
        self.repo.save(research)

        audit = AuditEntry(
            actor="pipeline",
            action="REPORT_GENERATED",
            object_id=report.id,
            object_type="ResearchReport",
            before_state="",
            after_state=report.to_json(),
        )
        self.repo.save(audit)

        return report

    # ------------------------------------------------------------------
    # Stage 9: Research → Validation
    # ------------------------------------------------------------------

    def validate_research(
        self,
        research_id: str,
        research_report_id: str,
        time_horizon: str = "",
        overall_status: str = "In Progress",
        quality_score: float = 0.0,
        scenario_results: list[dict[str, Any]] | None = None,
        target_results: list[dict[str, Any]] | None = None,
        validation_trace: str = "",
        ontology_tags: list[str] | None = None,
    ) -> Validation:
        """
        Validate research outputs against actual outcomes.
        """
        self.validator.require_exists(research_id, "Research")
        self.validator.require_exists(research_report_id, "ResearchReport")

        validation = Validation(
            research_id=research_id,
            research_report_id=research_report_id,
            time_horizon=time_horizon,
            overall_status=overall_status,
            quality_score=quality_score,
            scenario_results=scenario_results,
            target_results=target_results,
            validation_trace=validation_trace,
            ontology_tags=ontology_tags,
        )

        self.repo.save(validation)

        research = self.repo.get(research_id)
        research.validate()
        self.repo.save(research)

        audit = AuditEntry(
            actor="pipeline",
            action="VALIDATION_CREATED",
            object_id=validation.id,
            object_type="Validation",
            before_state="",
            after_state=validation.to_json(),
        )
        self.repo.save(audit)

        return validation

    def create_failure_analysis(
        self,
        validation_id: str,
        research_id: str,
        failures: list[dict[str, Any]] | None = None,
        root_causes: list[str] | None = None,
        severity_scores: list[dict[str, Any]] | None = None,
        improvement_areas: list[str] | None = None,
        failure_trace: str = "",
        ontology_tags: list[str] | None = None,
    ) -> FailureAnalysis:
        """
        Analyze failures identified during validation.
        """
        self.validator.require_exists(validation_id, "Validation")
        self.validator.require_exists(research_id, "Research")

        analysis = FailureAnalysis(
            validation_id=validation_id,
            research_id=research_id,
            failures=failures,
            root_causes=root_causes,
            severity_scores=severity_scores,
            improvement_areas=improvement_areas,
            failure_trace=failure_trace,
            ontology_tags=ontology_tags,
        )

        self.repo.save(analysis)

        audit = AuditEntry(
            actor="pipeline",
            action="FAILURE_ANALYSIS_CREATED",
            object_id=analysis.id,
            object_type="FailureAnalysis",
            before_state="",
            after_state=analysis.to_json(),
        )
        self.repo.save(audit)

        return analysis

    # ------------------------------------------------------------------
    # Stage 10: Validation → Knowledge
    # ------------------------------------------------------------------

    def extract_knowledge(
        self,
        type: str,
        subject: str,
        predicate: str,
        object: str,
        confidence: float = 0.0,
        evidence_count: int = 0,
        source_references: list[str] | None = None,
        knowledge_trace: str = "",
        ontology_tags: list[str] | None = None,
    ) -> Knowledge:
        """
        Record a knowledge item extracted from research validation.
        """
        for ref in source_references or []:
            self.validator.require_exists(ref, "Research")

        knowledge = Knowledge(
            type=type,
            subject=subject,
            predicate=predicate,
            object=object,
            confidence=confidence,
            evidence_count=evidence_count,
            source_references=source_references,
            knowledge_trace=knowledge_trace,
            ontology_tags=ontology_tags,
        )

        self.repo.save(knowledge)

        audit = AuditEntry(
            actor="pipeline",
            action="KNOWLEDGE_CREATED",
            object_id=knowledge.id,
            object_type="Knowledge",
            before_state="",
            after_state=knowledge.to_json(),
        )
        self.repo.save(audit)

        return knowledge

    def extract_lesson(
        self,
        type: str,
        description: str,
        recommendation: str = "",
        severity: float = 0.0,
        frequency: int = 0,
        affected_articles: list[str] | None = None,
        supporting_evidence: list[str] | None = None,
        lesson_trace: str = "",
        ontology_tags: list[str] | None = None,
    ) -> Lesson:
        """
        Record a lesson learned from validation.
        """
        lesson = Lesson(
            type=type,
            description=description,
            recommendation=recommendation,
            severity=severity,
            frequency=frequency,
            affected_articles=affected_articles,
            supporting_evidence=supporting_evidence,
            lesson_trace=lesson_trace,
            ontology_tags=ontology_tags,
        )

        self.repo.save(lesson)

        audit = AuditEntry(
            actor="pipeline",
            action="LESSON_EXTRACTED",
            object_id=lesson.id,
            object_type="Lesson",
            before_state="",
            after_state=lesson.to_json(),
        )
        self.repo.save(audit)

        return lesson

    # ------------------------------------------------------------------
    # Stage 11: Knowledge → Cognitive
    # ------------------------------------------------------------------

    def assess_cognitive(
        self,
        trader_id: str,
        research_id: str = "",
        knowledge_score: float = 0.0,
        reasoning_score: float = 0.0,
        bias_profile: list[str] | None = None,
        discipline_score: float = 0.0,
        reflection_score: float = 0.0,
        learning_progress: float = 0.0,
        overall_score: float = 0.0,
        feedback: list[str] | None = None,
        recommendations: list[str] | None = None,
        assessment_trace: str = "",
        ontology_tags: list[str] | None = None,
    ) -> CognitiveAssessment:
        """
        Create a cognitive assessment for a trader.
        """
        if research_id:
            self.validator.require_exists(research_id, "Research")

        assessment = CognitiveAssessment(
            trader_id=trader_id,
            research_id=research_id,
            knowledge_score=knowledge_score,
            reasoning_score=reasoning_score,
            bias_profile=bias_profile,
            discipline_score=discipline_score,
            reflection_score=reflection_score,
            learning_progress=learning_progress,
            overall_score=overall_score,
            feedback=feedback,
            recommendations=recommendations,
            assessment_trace=assessment_trace,
            ontology_tags=ontology_tags,
        )

        self.repo.save(assessment)

        audit = AuditEntry(
            actor="pipeline",
            action="COGNITIVE_ASSESSED",
            object_id=assessment.id,
            object_type="CognitiveAssessment",
            before_state="",
            after_state=assessment.to_json(),
        )
        self.repo.save(audit)

        return assessment

    # ------------------------------------------------------------------
    # Utility: Reasoning chain recording
    # ------------------------------------------------------------------

    def record_reasoning_chain(
        self,
        research_id: str,
        steps: list[dict[str, Any]] | None = None,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
        rules_applied: list[str] | None = None,
        evidence_used: list[str] | None = None,
        confidence: float = 0.0,
        trace: str = "",
        ontology_tags: list[str] | None = None,
    ) -> ReasoningChain:
        """
        Record a reasoning chain for auditability.
        """
        self.validator.require_exists(research_id, "Research")

        chain = ReasoningChain(
            research_id=research_id,
            steps=steps,
            inputs=inputs,
            outputs=outputs,
            rules_applied=rules_applied,
            evidence_used=evidence_used,
            confidence=confidence,
            trace=trace,
            ontology_tags=ontology_tags,
        )

        self.repo.save(chain)

        audit = AuditEntry(
            actor="pipeline",
            action="REASONING_CHAIN_RECORDED",
            object_id=chain.id,
            object_type="ReasoningChain",
            before_state="",
            after_state=chain.to_json(),
        )
        self.repo.save(audit)

        return chain
