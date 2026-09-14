"""API-first boundary from validated research evidence to knowledge proposals.

Phase 4 establishes a deterministic, auditable bridge:
Research -> Evidence -> Learning -> Knowledge.

The boundary deliberately emits immutable knowledge proposals instead of
mutating the legacy Knowledge/Pattern/Lesson objects directly. This keeps the
learning layer testable and prevents an experiment result from silently
becoming accepted knowledge without an explicit derivation record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LEARNING_BOUNDARY_SCHEMA_VERSION = "learning-boundary.v1"
KnowledgeKind = Literal["knowledge", "pattern", "lesson"]
LearningOutcome = Literal["accepted", "rejected", "inconclusive"]


@dataclass(frozen=True)
class LearningInput:
    """Immutable input to the learning/knowledge boundary."""

    schema_version: str
    research_id: str
    experiment_id: str
    validation_id: str
    hypothesis_id: str
    dataset_id: str
    dataset_content_hash: str
    evidence_collection_id: str
    evidence_hash: str
    learning_record_id: str
    learning_outcome: LearningOutcome
    confidence: float
    findings: tuple[str, ...] = ()
    patterns_observed: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != LEARNING_BOUNDARY_SCHEMA_VERSION:
            raise ValueError("unsupported learning boundary schema version")
        for name, value in (
            ("research_id", self.research_id),
            ("experiment_id", self.experiment_id),
            ("validation_id", self.validation_id),
            ("hypothesis_id", self.hypothesis_id),
            ("dataset_id", self.dataset_id),
            ("dataset_content_hash", self.dataset_content_hash),
            ("evidence_collection_id", self.evidence_collection_id),
            ("evidence_hash", self.evidence_hash),
            ("learning_record_id", self.learning_record_id),
        ):
            if not value:
                raise ValueError(f"{name} is required")
        if self.learning_outcome not in {"accepted", "rejected", "inconclusive"}:
            raise ValueError("learning_outcome must be accepted, rejected, or inconclusive")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "research_id": self.research_id,
            "experiment_id": self.experiment_id,
            "validation_id": self.validation_id,
            "hypothesis_id": self.hypothesis_id,
            "dataset_id": self.dataset_id,
            "dataset_content_hash": self.dataset_content_hash,
            "evidence_collection_id": self.evidence_collection_id,
            "evidence_hash": self.evidence_hash,
            "learning_record_id": self.learning_record_id,
            "learning_outcome": self.learning_outcome,
            "confidence": self.confidence,
            "findings": list(self.findings),
            "patterns_observed": list(self.patterns_observed),
            "recommendations": list(self.recommendations),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> LearningInput:
        return cls(
            schema_version=str(data["schema_version"]),
            research_id=str(data["research_id"]),
            experiment_id=str(data["experiment_id"]),
            validation_id=str(data["validation_id"]),
            hypothesis_id=str(data["hypothesis_id"]),
            dataset_id=str(data["dataset_id"]),
            dataset_content_hash=str(data["dataset_content_hash"]),
            evidence_collection_id=str(data["evidence_collection_id"]),
            evidence_hash=str(data["evidence_hash"]),
            learning_record_id=str(data["learning_record_id"]),
            learning_outcome=str(data["learning_outcome"]),
            confidence=float(data["confidence"]),
            findings=tuple(str(x) for x in data.get("findings", [])),
            patterns_observed=tuple(str(x) for x in data.get("patterns_observed", [])),
            recommendations=tuple(str(x) for x in data.get("recommendations", [])),
        )


@dataclass(frozen=True)
class KnowledgeProposal:
    """Immutable proposal for a knowledge-layer object.

    A proposal is not accepted knowledge. A separate persistence/approval
    layer can materialize it as Knowledge, Pattern, or Lesson after review.
    """

    schema_version: str
    proposal_id: str
    kind: KnowledgeKind
    research_id: str
    evidence_collection_id: str
    evidence_hash: str
    learning_record_id: str
    statement: str
    confidence: float
    supporting_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != LEARNING_BOUNDARY_SCHEMA_VERSION:
            raise ValueError("unsupported learning boundary schema version")
        if self.kind not in {"knowledge", "pattern", "lesson"}:
            raise ValueError("unsupported knowledge proposal kind")
        for name, value in (
            ("proposal_id", self.proposal_id),
            ("research_id", self.research_id),
            ("evidence_collection_id", self.evidence_collection_id),
            ("evidence_hash", self.evidence_hash),
            ("learning_record_id", self.learning_record_id),
            ("statement", self.statement),
        ):
            if not value:
                raise ValueError(f"{name} is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "kind": self.kind,
            "research_id": self.research_id,
            "evidence_collection_id": self.evidence_collection_id,
            "evidence_hash": self.evidence_hash,
            "learning_record_id": self.learning_record_id,
            "statement": self.statement,
            "confidence": self.confidence,
            "supporting_ids": list(self.supporting_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> KnowledgeProposal:
        return cls(
            schema_version=str(data["schema_version"]),
            proposal_id=str(data["proposal_id"]),
            kind=str(data["kind"]),
            research_id=str(data["research_id"]),
            evidence_collection_id=str(data["evidence_collection_id"]),
            evidence_hash=str(data["evidence_hash"]),
            learning_record_id=str(data["learning_record_id"]),
            statement=str(data["statement"]),
            confidence=float(data["confidence"]),
            supporting_ids=tuple(str(x) for x in data.get("supporting_ids", [])),
        )


def build_learning_input(
    *,
    research_id: str,
    experiment_id: str,
    validation_id: str,
    hypothesis_id: str,
    dataset_id: str,
    dataset_content_hash: str,
    evidence_collection_id: str,
    evidence_hash: str,
    learning_record_id: str,
    learning_outcome: LearningOutcome,
    confidence: float,
    findings: list[str] | tuple[str, ...] = (),
    patterns_observed: list[str] | tuple[str, ...] = (),
    recommendations: list[str] | tuple[str, ...] = (),
) -> LearningInput:
    """Create the canonical learning input while preserving full lineage."""
    return LearningInput(
        schema_version=LEARNING_BOUNDARY_SCHEMA_VERSION,
        research_id=research_id,
        experiment_id=experiment_id,
        validation_id=validation_id,
        hypothesis_id=hypothesis_id,
        dataset_id=dataset_id,
        dataset_content_hash=dataset_content_hash,
        evidence_collection_id=evidence_collection_id,
        evidence_hash=evidence_hash,
        learning_record_id=learning_record_id,
        learning_outcome=learning_outcome,
        confidence=confidence,
        findings=tuple(findings),
        patterns_observed=tuple(patterns_observed),
        recommendations=tuple(recommendations),
    )


def proposals_from_learning(learning: LearningInput) -> tuple[KnowledgeProposal, ...]:
    """Derive deterministic proposals without silently accepting knowledge.

    Accepted findings become knowledge proposals, observed recurring patterns
    become pattern proposals, and recommendations become lesson proposals.
    Rejected/inconclusive outcomes may still produce lessons, but never create
    an accepted knowledge proposal from an empty finding.
    """
    proposals: list[KnowledgeProposal] = []

    def add(kind: KnowledgeKind, index: int, statement: str, ids: tuple[str, ...]) -> None:
        proposal_id = (
            f"{learning.learning_record_id}:{kind}:{index}"
        )
        proposals.append(
            KnowledgeProposal(
                schema_version=LEARNING_BOUNDARY_SCHEMA_VERSION,
                proposal_id=proposal_id,
                kind=kind,
                research_id=learning.research_id,
                evidence_collection_id=learning.evidence_collection_id,
                evidence_hash=learning.evidence_hash,
                learning_record_id=learning.learning_record_id,
                statement=statement,
                confidence=learning.confidence,
                supporting_ids=ids,
            )
        )

    if learning.learning_outcome == "accepted":
        for index, finding in enumerate(learning.findings):
            add("knowledge", index, finding, (learning.validation_id, learning.evidence_collection_id))

    for index, pattern in enumerate(learning.patterns_observed):
        add("pattern", index, pattern, (learning.experiment_id, learning.evidence_collection_id))

    for index, recommendation in enumerate(learning.recommendations):
        add("lesson", index, recommendation, (learning.validation_id, learning.evidence_collection_id))

    return tuple(proposals)
