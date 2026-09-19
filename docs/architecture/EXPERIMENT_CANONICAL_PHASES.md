# Canonical Experiment Phases

## Phase 5.1

researchos.experiments.phase51 is the frozen baseline experiment. It remains
read-only except for compatibility or explicitly versioned corrections.

## Phase 5.2

researchos.experiments.phase52 contains the original macro-augmented
implementation and remains supported for reproducibility of existing
artifacts and tests.

## Phase 5.2 Rebuild

researchos.experiments.phase52_rebuild is the canonical forward-development
path for Phase 5.2 data construction, feature contracts, provenance, context
audits, and reproducibility gates.

It may reuse stable Phase 5.2 primitives, but new dataset/provenance logic
must land in the rebuild namespace.

## Rule

Do not delete phase51 or phase52 merely to remove naming ambiguity. The
ambiguity is resolved by lifecycle:
- phase51 = frozen baseline
- phase52 = compatibility/reproducibility
- phase52_rebuild = canonical active implementation

A future major-version migration may retire phase52 only after all consumers
and reproducibility artifacts are migrated and the full test/evidence surface
is green.
