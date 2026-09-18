# QROS Research Intelligence v1

Status: **implemented as a deterministic planning foundation**

Research Intelligence v1 is the decision layer between research facts and numerical
execution. It does not use an LLM to choose a method and it does not optimize for
a desirable result.

## Computational contract

`ResearchContext → CapabilityRegistry → ResearchPlanner → ComputePlan → ValidationPlan`

The planner may select a method only when its declared prerequisites are satisfied:
analysis class, required features, sample size, temporal ordering, dependence,
out-of-sample state, and post-hoc policy.

Every selected path records:
- method and version;
- numerical backend;
- dataset identity;
- explicit selection reason;
- rejected candidates and their reasons;
- deterministic SHA-256 plan identity.

The validation plan always includes dataset integrity, method prerequisites,
look-ahead protection, provenance, and reproducibility. Multiple-testing,
post-hoc, and OOS checks are added when those facts apply.

## Design boundary

This is intentionally a foundation, not a claim that QROS can already choose every
method in the 2026 analysis execution contract. The registry must grow only by
adding governed methods with explicit prerequisites and tests.

The planner also does not execute computations. It produces an auditable route for
a later execution engine.

## Next stages

1. Bind planner output to governed AnalysisResult.
2. Add actual numerical capability adapters (vector/matrix/statistical backends).
3. Add evidence emission from the validated result.
4. Add SaaS research-run integration.
5. Add leakage and data-sufficiency gates backed by real dataset metadata.
