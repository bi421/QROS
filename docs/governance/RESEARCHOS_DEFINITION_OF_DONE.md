# ResearchOS Definition of Done & Quality Gates

**Status:** Mandatory 1.0  
**Date:** 2026-09-17

## Gate 0 — Scope

Every change must declare which boundary it affects:

- research core;
- data integrity;
- probability/edge engine;
- C++ engine;
- evidence/knowledge;
- SaaS control plane;
- infrastructure;
- future execution plane.

Changes must not cross a boundary accidentally.

## Gate 1 — Contract

Before implementation, the behavior must be expressible as a testable contract:

`inputs → trigger → calculation → outputs → failure behavior → provenance`

## Gate 2 — Correctness

Required as applicable:

- unit tests;
- property/edge-case tests;
- integration tests;
- regression tests;
- numerical reference/differential tests for critical quantitative code.

## Gate 3 — Research integrity

A research feature must preserve:

- data provenance;
- temporal integrity;
- no silent repair;
- explicit train/validation/test semantics;
- search/selection accounting;
- reproducibility;
- failure visibility.

## Gate 4 — Determinism

For deterministic research jobs, rerunning the same immutable inputs must produce equivalent output within a documented tolerance. Randomized algorithms must record seed and algorithm/version where reproducibility is required.

## Gate 5 — Performance

Performance-sensitive changes require a before/after benchmark. A benchmark must state workload size, environment, repeat count, and metric. A speedup without numerical equivalence is not accepted as an optimization win.

## Gate 6 — Security

SaaS changes require authorization tests and tenant-boundary tests. Secrets must not enter source control or result artifacts. External input must be validated at the boundary.

## Gate 7 — Documentation

The change must update the relevant contract/architecture document when behavior or public semantics change.

## Gate 8 — CI

Required CI checks must pass. A local green result cannot override a failed CI gate. A GitHub green result is not evidence that a capability exists if the capability was not actually exercised by the workflow.

## Gate 9 — Release evidence

Release notes must distinguish:

- implemented;
- tested;
- benchmarked;
- experimentally validated;
- production-ready.

These are different states.

## Risk classes

### R0 — Documentation only

No runtime behavior.

### R1 — Pure deterministic utility

Small surface; unit + edge tests.

### R2 — Quantitative method

Unit + statistical properties + reference/differential tests + provenance contract.

### R3 — Evidence/knowledge mutation

R2 plus lineage, authorization where applicable, rollback/rejection behavior.

### R4 — SaaS/security boundary

R3 plus tenant isolation, authorization, audit, failure containment.

### R5 — Execution/financial side effect

Separate execution review, risk controls, kill-switch semantics, integration tests, replay/simulation evidence, and explicit approval. R5 code must never be silently introduced into Research Core.

## Merge rule

No change may be described as complete while a required gate is pending. Pending work is explicitly labeled pending.
