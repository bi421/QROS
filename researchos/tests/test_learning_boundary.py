"""Tests for the Phase 4 Research -> Evidence -> Knowledge boundary."""

import pytest

from researchos.learning_boundary import (
    LEARNING_BOUNDARY_SCHEMA_VERSION,
    KnowledgeProposal,
    LearningInput,
    build_learning_input,
    proposals_from_learning,
)


def _learning() -> LearningInput:
    return build_learning_input(
        research_id="research-001",
        experiment_id="experiment-001",
        validation_id="validation-001",
        hypothesis_id="hypothesis-001",
        dataset_id="dataset-001",
        dataset_content_hash="content-hash-001",
        evidence_collection_id="evidence-001",
        evidence_hash="evidence-hash-001",
        learning_record_id="learning-001",
        learning_outcome="accepted",
        confidence=0.8,
        findings=["The event response was repeatable in the validated sample."],
        patterns_observed=["H1 response clustered after the defined event."],
        recommendations=["Replicate the finding on an out-of-sample period."],
    )


def test_learning_input_is_immutable_and_round_trips() -> None:
    learning = _learning()
    assert learning.schema_version == LEARNING_BOUNDARY_SCHEMA_VERSION
    assert LearningInput.from_dict(learning.to_dict()) == learning
    with pytest.raises(AttributeError):
        learning.confidence = 0.9  # type: ignore[misc]


def test_learning_input_requires_full_lineage() -> None:
    with pytest.raises(ValueError, match="evidence_hash is required"):
        build_learning_input(
            research_id="research-001",
            experiment_id="experiment-001",
            validation_id="validation-001",
            hypothesis_id="hypothesis-001",
            dataset_id="dataset-001",
            dataset_content_hash="content-hash-001",
            evidence_collection_id="evidence-001",
            evidence_hash="",
            learning_record_id="learning-001",
            learning_outcome="accepted",
            confidence=0.8,
        )


def test_accepted_learning_produces_deterministic_proposals() -> None:
    learning = _learning()
    first = proposals_from_learning(learning)
    second = proposals_from_learning(learning)

    assert first == second
    assert [p.kind for p in first] == ["knowledge", "pattern", "lesson"]
    assert all(p.evidence_hash == learning.evidence_hash for p in first)
    assert first[0].statement == learning.findings[0]


def test_rejected_learning_does_not_create_accepted_knowledge() -> None:
    learning = LearningInput.from_dict(
        {
            **_learning().to_dict(),
            "learning_outcome": "rejected",
        }
    )

    proposals = proposals_from_learning(learning)

    assert all(p.kind != "knowledge" for p in proposals)
    assert any(p.kind == "pattern" for p in proposals)
    assert any(p.kind == "lesson" for p in proposals)


def test_inconclusive_learning_can_emit_lessons_but_not_knowledge() -> None:
    learning = LearningInput.from_dict(
        {
            **_learning().to_dict(),
            "learning_outcome": "inconclusive",
        }
    )

    proposals = proposals_from_learning(learning)

    assert all(p.kind != "knowledge" for p in proposals)
    assert [p.kind for p in proposals] == ["pattern", "lesson"]


def test_knowledge_proposal_round_trip_preserves_lineage() -> None:
    proposal = proposals_from_learning(_learning())[0]
    restored = KnowledgeProposal.from_dict(proposal.to_dict())

    assert restored == proposal
    assert restored.research_id == "research-001"
    assert restored.evidence_collection_id == "evidence-001"
    assert restored.evidence_hash == "evidence-hash-001"
