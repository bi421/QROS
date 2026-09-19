# ResearchOS Quant Research Operating System — Governance Charter

**Status:** Proposed mandatory engineering standard 1.0  
**Date:** 2026-09-17  
**Applies to:** ResearchOS repository, research engines, probability/edge analysis, data pipelines, SaaS surfaces, and any future execution integration.

## 1. Mission

ResearchOS is a **Quant Research Operating System (QROS)**. Its primary job is not to generate trading signals or maximize backtest returns. Its job is to make quantitative research **traceable, reproducible, falsifiable, uncertainty-aware, selection-aware, and economically testable**.

The canonical research loop is:

`CLAIM → PLAN LOCK → DATA INTEGRITY → OBSERVATIONS → ANALYSIS → VALIDATION → EVIDENCE → REPLICATION → KNOWLEDGE STATUS`

A result that cannot be traced through this chain is not eligible to become durable knowledge.

## 2. Non-negotiable invariants

1. **Evidence before intelligence.** AI/ML may accelerate research, but cannot replace empirical evidence.
2. **No silent data repair.** Interpolation, forward fill, synthetic bars, hidden resampling, and undocumented corrections are prohibited.
3. **No hidden selection.** Search count, variants, parameter sweeps, failed experiments, and discarded candidates must remain auditable.
4. **No single-score truth.** Probability, payoff, uncertainty, risk, tail behavior, dependence, calibration, OOS performance, and replication remain inspectable dimensions.
5. **No knowledge promotion from one lucky run.** Durable Knowledge requires explicit validation and promotion criteria.
6. **Determinism by default.** The same data/config/code version must reproduce the same result within a documented numerical tolerance.
7. **Provenance is part of the result.** Dataset version, hash, feature/label version, code revision, configuration, environment, and analysis method must be recorded.
8. **Research and execution are separate trust domains.** Live execution cannot be introduced into the research core as an implicit side effect.
9. **Failure is evidence.** Negative, contradictory, inconclusive, invalid, and rejected experiments are first-class research records.
10. **Uncertainty must not be hidden.** Point estimates without uncertainty are incomplete for claims where estimation uncertainty is material.
11. **Performance claims require economic costs.** Gross returns do not establish an economic edge.
12. **Security and tenant isolation are correctness requirements for SaaS.** They are not optional production polish.

## 3. Research object hierarchy

```text
Research Claim
  └─ Research Plan Lock
      └─ Dataset / Data Integrity Envelope
          └─ Experiment
              └─ Run
                  └─ Result
                      └─ Analysis Artifacts
                          └─ Validation
                              └─ Finding
                                  └─ Replication / Contradiction
                                      └─ Knowledge Status
```

`LearningRecord` may describe the research process, but must not bypass validation to become canonical Knowledge.

## 4. Mandatory analysis contract

Every quantitative analysis must declare:

- purpose;
- trigger/eligibility condition;
- input schema;
- population definition;
- time horizon;
- data version/hash;
- assumptions;
- method/model version;
- sample size and effective sample size when meaningful;
- point estimate;
- uncertainty interval or an explicit reason it is not applicable;
- diagnostics;
- warnings/limitations;
- downstream consumers;
- artifact hash;
- integrity/OOS/replication/calibration status.

## 5. Formula governance

The Probability & Edge Engine must treat methods as composable, versioned services. At minimum the governed families are:

- probability: conditional probability, Bayes, binomial/Beta-Binomial;
- payoff: expected value, Kelly sizing mathematics;
- uncertainty: IID/bootstrap only when defensible, block/stationary bootstrap;
- risk: VaR, Expected Shortfall, drawdown;
- econometrics: stationarity, autocorrelation, ARIMA-family, GARCH-family;
- stochastic processes: GBM, Ornstein-Uhlenbeck and explicit assumption checks;
- distributions/tails: Student-t, EVT;
- dependence: copulas and tail dependence;
- information: Shannon entropy, conditional entropy, mutual information;
- inference: Sharpe uncertainty, PSR, DSR;
- selection bias: multiple testing, Reality Check, SPA, PBO, CPCV, purging/embargo;
- calibration: reliability, Brier score, log loss, calibration slope/intercept.

A formula is not a claim. A model fit is not a validated edge. A statistically significant result is not automatically an economically significant result.

## 6. Technology admission rules

A new dependency must answer:

1. What ResearchOS responsibility does it serve?
2. Why is the current standard library insufficient?
3. What deterministic contract does it implement?
4. What are its numerical/performance implications?
5. Does it duplicate an existing dependency?
6. How will it be tested and pinned?
7. What happens if it becomes unavailable or unmaintained?
8. Does it cross the research/execution trust boundary?

No library is added merely because it is popular.

## 7. Performance governance

Performance work must be evidence-driven. Every optimization must preserve numerical semantics unless a contract explicitly permits approximation.

Required measurements where performance is material:

- wall-clock latency;
- throughput;
- memory allocation/peak memory;
- dataset size;
- warm/cold behavior where relevant;
- reproducibility;
- numerical error/tolerance.

C++ is the preferred implementation layer for compute-heavy deterministic kernels when profiling demonstrates a material benefit. Python remains the primary research orchestration and exploratory layer.

## 8. Research/execution boundary

ResearchOS Core does not place live orders. A future Execution System may consume **validated, versioned research artifacts** through a one-way, explicit interface.

No research function may contain an implicit broker/exchange side effect.

## 9. SaaS governance

Before production SaaS release, the system must provide:

- authentication;
- tenant isolation;
- authorization/RLS;
- immutable-ish audit events for sensitive actions;
- secret isolation;
- API validation/rate limits;
- artifact access control;
- job isolation;
- billing/metering boundaries;
- backup/recovery policy;
- observability;
- data retention/deletion policy.

## 10. Definition of Done

A feature is not Done because its code exists. It is Done only when:

`DESIGN → CONTRACT → IMPLEMENTATION → UNIT TEST → INTEGRATION TEST → FAILURE TEST → DETERMINISM CHECK → PERFORMANCE CHECK (if applicable) → DOCUMENTATION → CI → REVIEW → MERGE`

has been satisfied for the feature's risk class.

## 11. Forbidden shortcuts

- deleting failing tests to make CI green;
- weakening assertions without a documented contract change;
- hiding exceptions behind broad catches;
- skipping provenance to simplify APIs;
- silently changing dataset semantics;
- replacing a failing statistical method with a weaker method without disclosure;
- treating an LLM answer as numerical evidence;
- adding live trading side effects to research code;
- merging code that has not passed the applicable CI gates.

## 12. Decision authority

When speed conflicts with evidence integrity, **evidence integrity wins**.

When abstraction conflicts with measured performance, profile first.

When a feature conflicts with the research boundary, isolate the feature rather than weakening the boundary.

When uncertainty is material and cannot be quantified, the result must be labeled accordingly rather than presented as precise.

## 13. Security architecture control

The mandatory security and architecture invariants are defined in `docs/governance/SECURITY_ARCHITECTURE_GOVERNANCE.md`. Trust-boundary changes are classified R0-R3 and must satisfy the corresponding evidence gates before merge.

## 13. Release gate

A ResearchOS release may claim a research capability only when its capability contract, tests, provenance, and applicable CI evidence exist in the repository. Marketing language must not exceed the verified implementation state.
