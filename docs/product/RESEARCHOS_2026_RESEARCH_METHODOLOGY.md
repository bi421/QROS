# ResearchOS 2026 Research Methodology

**Status:** Proposed product standard 0.1  
**Date:** 2026-09-17  
**Scope:** Quantitative research SaaS methodology and architecture contract

## 1. Purpose

ResearchOS is designed to help a researcher establish, challenge, reproduce, and retain empirical claims about financial markets.

It is not designed to maximize the number of strategies discovered, the number of positive backtests, or the speed at which a model reaches deployment.

The primary unit of research is a **Research Claim**. A claim is a falsifiable statement whose evidence history can be inspected and reproduced.

## 2. Design principle: evidence before intelligence

No AI-generated idea, statistic, optimization result, chart, narrative, or recommendation is evidence by itself.

AI may propose work. Deterministic computation and recorded empirical artifacts establish evidence.

```text
QUESTION
  ↓
CLAIM
  ↓
RESEARCH PLAN
  ↓
DATA CONTRACT
  ↓
EXPERIMENT
  ↓
VALIDATION
  ↓
FINDING
  ↓
REPLICATION
  ↓
EVIDENCE STATE
  ↓
KNOWLEDGE
```

## 3. Research Claim contract

Every claim must have:

- stable claim ID;
- exact statement;
- claim type;
- target population/instrument;
- observation horizon;
- timestamp policy;
- economic rationale or prior;
- falsification conditions;
- primary metric(s);
- minimum evidence requirements;
- declared research plan;
- creation timestamp;
- creator and workspace;
- lineage to all derived hypotheses and experiments.

A claim cannot silently change meaning after experiments have begun. Material changes create a new claim version or a new claim.

## 4. Research Plan Lock

Before a confirmatory experiment is executed, ResearchOS should allow the researcher to commit a machine-readable analysis plan.

The plan records:

- hypothesis;
- sample definition;
- feature definitions;
- labels;
- train/validation/test policy;
- exclusion rules;
- costs and slippage assumptions;
- statistical tests;
- primary and secondary metrics;
- stopping rules;
- multiple-testing policy;
- replication policy.

The plan receives a content hash. Post-hoc changes are never silently merged into the original plan.

Exploratory research remains allowed, but exploratory and confirmatory evidence are explicitly distinguished.

## 5. Data Integrity Envelope

Every dataset used in evidence-producing research must carry a provenance envelope containing:

- source identity;
- source version where available;
- retrieval time;
- coverage interval;
- timezone/calendar policy;
- schema version;
- file/object hashes;
- row/record counts;
- duplicate policy;
- missingness summary;
- gap summary;
- corporate-action/contract-roll treatment where relevant;
- point-in-time availability policy;
- transformation lineage.

Synthetic repair, interpolation, forward filling, or silent deletion is prohibited unless explicitly declared as a transformation with its own artifact and rationale.

## 6. Temporal Integrity Gate

Financial research must be evaluated under information availability at decision time.

The gate checks, where applicable:

- look-ahead leakage;
- future-data joins;
- publication/release timestamp mismatch;
- feature availability timing;
- label overlap;
- train/test contamination;
- survivorship and selection bias;
- corporate-action leakage;
- timezone/session boundary errors.

A passing backtest metric cannot override a failed temporal-integrity gate.

## 7. Experiment classes

ResearchOS distinguishes at least four experiment classes:

### Exploratory

Used to discover possible relationships. Results are hypothesis-generating and are not automatically treated as confirmatory evidence.

### Confirmatory

Executed against a locked research plan with predeclared primary tests and acceptance criteria.

### Robustness

Tests sensitivity to reasonable changes in assumptions, parameters, periods, costs, universes, and regimes.

### Replication

Re-executes a claim using an independently defined dataset, period, implementation, or researcher path as required by the replication contract.

## 8. Anti-overfitting methodology

ResearchOS should treat model selection as a source of statistical risk rather than as neutral optimization.

The methodology should support, as appropriate to the research design:

- holdout testing;
- walk-forward evaluation;
- purged/embargoed cross-validation;
- combinatorial purged cross-validation where applicable;
- Probability of Backtest Overfitting diagnostics;
- Deflated Sharpe Ratio or equivalent multiple-testing adjustment;
- White's Reality Check / Hansen SPA where applicable;
- multiple-hypothesis correction;
- parameter sensitivity analysis;
- placebo/falsification tests;
- benchmark and naive-model comparisons.

No single statistic is sufficient evidence of robustness.

## 9. Research Budget and Multiple Testing Ledger

Every workspace should maintain a research ledger describing how many materially distinct hypotheses, parameterizations, datasets, model families, and selection attempts contributed to a claimed result.

The purpose is not to punish exploration. It is to prevent a final positive result from being interpreted without the search history that produced it.

The ledger must distinguish:

- planned tests;
- exploratory tests;
- failed tests;
- discarded tests;
- selected tests;
- duplicated/reproduced tests.

## 10. Contradiction is first-class evidence

Evidence storage must not be optimized around positive results.

For every claim, the evidence model must represent:

```text
SUPPORTING
CONTRADICTING
INCONCLUSIVE
FAILED_VALIDATION
REPLICATED
NOT_REPLICATED
```

A contradictory result remains attached to the claim even when a later result is positive.

## 11. Evidence State Machine

The user-facing state is derived from evidence and configured gates, not manually typed by an AI assistant.

```text
UNTESTED
   ↓
TESTED
   ├── INCONCLUSIVE
   ├── CONTRADICTED
   └── CANDIDATE
          ↓
      ROBUSTNESS
          ↓
      REPLICATION
          ↓
      SUPPORTED
```

`REJECTED` is reserved for an explicit failed gate or declared falsification rule.

The exact transition rules must be versioned and auditable.

## 12. Evidence Independence

Repeated experiments using the same data, same feature construction, same period, or materially identical code are not automatically independent evidence.

ResearchOS should compute and display evidence-dependence metadata so users cannot mistake repeated runs for repeated discoveries.

## 13. Evidence Graph

The product should represent research as a graph rather than a flat list of backtests.

```text
Claim
 ├── Hypothesis
 ├── Plan
 ├── Dataset versions
 ├── Experiments
 │    ├── Runs
 │    ├── Metrics
 │    └── Artifacts
 ├── Validation gates
 ├── Findings
 ├── Replications
 ├── Contradictions
 └── Knowledge records
```

Every derived artifact must have machine-readable parent lineage.

## 14. Reproduction contract

A result is reproducible only if ResearchOS can identify the required:

- source data;
- dataset version/hash;
- code/version;
- environment/dependencies;
- configuration;
- random seeds where applicable;
- analysis-plan version;
- execution engine version;
- output artifact hashes.

Reproduction status must be explicit:

`REPRODUCIBLE`, `PARTIALLY_REPRODUCIBLE`, or `NOT_REPRODUCIBLE`.

## 15. Knowledge promotion

Durable Knowledge is not a cache of AI summaries.

Promotion requires a validated Finding with complete lineage and a configured evidence threshold.

```text
Experiment
   ↓
Run
   ↓
Result
   ↓
Validation
   ↓
Finding
   ↓
Knowledge
```

This preserves the existing ResearchOS architectural boundary between learning and justified durable knowledge.

## 16. AI boundary

AI agents may:

- search prior research;
- propose hypotheses;
- draft analysis plans;
- generate code;
- identify possible contradictions;
- suggest robustness tests;
- summarize evidence;
- explain results.

AI agents may not silently:

- modify locked analysis plans;
- change dataset definitions;
- hide failed experiments;
- promote unvalidated findings to Knowledge;
- convert uncertainty into certainty;
- claim that a result is reproduced without an actual reproduction artifact.

Every agent action that changes research state must be logged as an auditable event.

## 17. Human control

High-impact transitions should require explicit researcher approval unless the workspace policy explicitly delegates them.

Examples:

- locking a confirmatory plan;
- declaring a primary metric;
- accepting a dataset transformation;
- promoting a Finding to Knowledge;
- changing evidence thresholds.

Automation should reduce work, not remove accountability.

## 18. Reproducible execution architecture

The execution layer should be content-addressed where practical.

A research result should be addressable by a deterministic identity derived from relevant inputs rather than by a mutable database row alone.

The architecture should support:

- immutable artifacts;
- append-only event history;
- deterministic manifests;
- versioned contracts;
- idempotent execution;
- retry-safe jobs;
- explicit failure states;
- replay from recorded inputs.

## 19. Multi-tenant SaaS boundary

The SaaS architecture must treat tenant isolation as a correctness property, not merely an authorization feature.

Every tenant-owned object must have an explicit ownership boundary and authorization policy.

The platform should support:

- workspace isolation;
- role-based permissions;
- row-level authorization;
- immutable audit events;
- encrypted secrets;
- usage metering;
- export and deletion workflows;
- disaster recovery procedures.

No shared cache, search index, vector store, background job, or artifact store may rely on implicit tenant context.

## 20. Version everything that can change meaning

The following are versioned contracts:

- data schema;
- dataset;
- feature definition;
- label definition;
- experiment;
- analysis plan;
- validation policy;
- evidence-state rules;
- metric definition;
- execution engine;
- AI agent/prompt/tool policy;
- report format.

A report must identify the versions that produced it.

## 21. Failure philosophy

ResearchOS must fail closed for evidence integrity.

If a required integrity condition cannot be established, the system should produce an explicit `UNKNOWN`/`BLOCKED` state rather than silently guessing, repairing, or downgrading the requirement.

Examples:

- unknown timestamp provenance;
- incomplete dataset coverage;
- unverifiable artifact hash;
- missing dependency lock;
- failed reproduction;
- ambiguous train/test boundary.

## 22. Future-proofing rule

No architecture can guarantee that future errors will never occur.

ResearchOS instead aims to make important errors:

1. difficult to introduce;
2. difficult to hide;
3. easy to detect;
4. easy to reproduce;
5. impossible to reinterpret silently;
6. recoverable without destroying historical evidence.

This is the definition of future-proofing used by the project.

## 23. Product acceptance test

The methodology is not considered implemented until a new user can perform this complete workflow without manually stitching files together:

```text
Create Claim
  ↓
Define Research Plan
  ↓
Lock Plan
  ↓
Attach Validated Dataset
  ↓
Run Exploratory Research
  ↓
Create Confirmatory Experiment
  ↓
Run Integrity Gates
  ↓
Run Robustness Tests
  ↓
Run Replication
  ↓
Review Supporting + Contradicting Evidence
  ↓
Inspect Research Search Budget
  ↓
Review Missing Evidence
  ↓
Receive Evidence State
  ↓
Approve Knowledge Promotion
  ↓
Reproduce the complete result later
```

## 24. Implementation order

The implementation order is intentionally different from a conventional SaaS build:

### Phase 0 — Contract

Freeze domain contracts and invariants before UI work.

### Phase 1 — Research Claim

Implement claim identity, versioning, plan lock, and lineage.

### Phase 2 — Evidence Graph

Unify experiment/run/result/validation/finding relationships into a queryable claim history.

### Phase 3 — Integrity Engine

Implement temporal integrity, provenance, reproducibility, and data-quality gates.

### Phase 4 — Research Memory

Implement related-claim discovery, contradiction tracking, evidence dependence, and search-budget accounting.

### Phase 5 — Replication

Implement independent replication contracts and reproducibility reports.

### Phase 6 — SaaS

Add tenant isolation, authentication, authorization, billing, metering, jobs, and audit infrastructure.

### Phase 7 — AI

Add grounded research agents only after deterministic evidence APIs are stable.

## 25. Core invariant

> **ResearchOS must never become more certain than its evidence.**

Every product feature, API, agent, database schema, report, and UI state must preserve this invariant.
