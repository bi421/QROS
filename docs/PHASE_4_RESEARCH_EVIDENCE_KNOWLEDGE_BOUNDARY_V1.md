# Phase 4 — Research → Evidence → Knowledge Boundary V1

## Objective

Make the learning path explicit and auditable without allowing experiment output to silently become accepted knowledge.

## Architecture

```text
ValidatedDatasetRef
        ↓
ResearchInput
        ↓
Research / Experiment
        ↓
ExperimentValidation
        ↓
EvidenceCollection
        ↓
ResearchEvidenceLink
        ↓
LearningInput
        ↓
KnowledgeProposal / PatternProposal / LessonProposal
        ↓
Explicit materialization / review
        ↓
Knowledge layer
```

## New contract

`researchos/learning_boundary.py` introduces two immutable API-first contracts:

- `LearningInput`: binds a learning record to research, experiment, validation, dataset content identity, evidence collection, and evidence hash.
- `KnowledgeProposal`: represents a derived knowledge-layer proposal while preserving research/evidence lineage.

`proposals_from_learning()` is deterministic and does not mutate `Knowledge`, `Pattern`, or `Lesson` objects.

## Safety rules

1. Accepted findings may produce `knowledge` proposals.
2. Rejected or inconclusive findings never produce accepted `knowledge` proposals.
3. Observed patterns and recommendations remain explicit `pattern` and `lesson` proposals.
4. Every proposal carries the originating research ID, evidence collection ID, evidence hash, and learning record ID.
5. Proposal generation is not knowledge acceptance; materialization remains an explicit later boundary.
6. No broker, order, autonomous execution, ML, LLM, or hidden trading logic is introduced.

## Why this boundary exists

ResearchOS already has legacy `LearningRecord`, `Knowledge`, `Pattern`, and `Lesson` objects. Phase 4 does not replace them. It adds a deterministic contract around their transition so the system can evolve without conflating:

- an experiment result,
- a learning statement,
- a recurring pattern,
- a lesson,
- and accepted long-term knowledge.

The distinction is essential for scientific reproducibility and prevents unsupported claims from becoming permanent system knowledge.

## Verification

`researchos/tests/test_learning_boundary.py` verifies:

- immutable and deterministic `LearningInput` serialization
- complete lineage requirements
- deterministic proposal generation
- rejection of accepted knowledge for rejected findings
- handling of inconclusive findings
- preservation of evidence lineage through proposal serialization
