# ResearchOS 2026 Research Methodology

**Status:** Proposed product standard 0.2  
**Date:** 2026-09-17  
**Scope:** Quantitative research SaaS methodology and architecture contract

## 1. Purpose

ResearchOS helps a researcher establish, challenge, reproduce, and retain empirical claims about financial markets. It is not designed to maximize positive backtests or deployment speed. The primary unit is a **Research Claim**: a falsifiable statement whose evidence history can be inspected and reproduced.

## 2. Evidence before intelligence

No AI-generated idea, statistic, optimization result, chart, narrative, or recommendation is evidence by itself. AI may propose work; deterministic computation and recorded empirical artifacts establish evidence.

```text
QUESTION → CLAIM → RESEARCH PLAN → DATA CONTRACT → EXPERIMENT → VALIDATION → FINDING → REPLICATION → EVIDENCE STATE → KNOWLEDGE
```

## 3. Research Claim contract

Every claim has a stable ID, exact statement, claim type, target population/instrument, horizon, timestamp policy, economic rationale, falsification conditions, primary metrics, minimum evidence requirements, declared research plan, creator/workspace and lineage to derived hypotheses/experiments. Material meaning changes create a new version or claim.

## 4. Research Plan Lock

Before a confirmatory experiment, a machine-readable plan records hypothesis, sample, features, labels, train/validation/test policy, exclusions, costs/slippage, statistical tests, metrics, stopping rules, multiple-testing policy and replication policy. The plan receives a content hash; post-hoc changes never silently modify the original. Exploratory and confirmatory evidence remain distinct.

## 5. Data Integrity Envelope

Evidence-producing datasets carry source identity/version, retrieval time, coverage, timezone/calendar policy, schema version, hashes, counts, duplicate/missingness/gap summaries, corporate-action/contract-roll treatment, point-in-time availability and transformation lineage. Synthetic repair, interpolation, forward fill or silent deletion is prohibited unless explicitly declared as a transformation artifact.

## 6. Temporal Integrity Gate

The gate checks look-ahead leakage, future joins, publication timestamp mismatch, feature availability timing, label overlap, train/test contamination, survivorship/selection bias, corporate-action leakage and timezone/session boundary errors. A favorable metric cannot override a failed integrity gate.

## 7. Probability & Trading-Edge Methodology

ResearchOS does not treat win rate as a sufficient measure of edge. Probability and edge analysis is a layered scientific measurement system. The complete standard is defined in `docs/product/RESEARCHOS_PROBABILITY_AND_EDGE_FRAMEWORK_2026.md`.

```text
OBSERVATIONS
  ↓
EVENT / RETURN DISTRIBUTION
  ↓
CONDITIONAL PROBABILITY
  ↓
EXPECTED PAYOFF + RISK
  ↓
ESTIMATION UNCERTAINTY
  ↓
DEPENDENCE + TIME-SERIES EFFECTS
  ↓
TAIL + EXTREME-EVENT ANALYSIS
  ↓
MULTIPLE TESTING / SELECTION BIAS
  ↓
OUT-OF-SAMPLE + ROBUSTNESS
  ↓
REPLICATION + CALIBRATION
  ↓
ECONOMIC EDGE ASSESSMENT
```

The framework includes, where justified by the research question:

- probability, Bayes, expected value, effect sizes and uncertainty intervals;
- Kelly/log-growth analysis with explicit estimation-risk caveats;
- time-series econometrics, stationarity, autocorrelation and volatility models including GARCH-family models;
- VaR and Expected Shortfall with declared sign conventions and tail assumptions;
- stochastic-process benchmarks such as GBM and Ornstein-Uhlenbeck, explicitly labeled as model assumptions rather than market truth;
- Student-t/heavy-tail models, Extreme Value Theory and copulas for non-Gaussian tails and dependence;
- Shannon entropy, conditional entropy, mutual information and information gain, without equating information-theoretic dependence to economic profitability;
- dependence-aware bootstrap/resampling;
- Sharpe uncertainty, Probabilistic Sharpe Ratio and Deflated Sharpe Ratio where appropriate;
- multiple-testing accounting, Probability of Backtest Overfitting, CPCV, purging/embargo, White Reality Check and Hansen SPA where appropriate;
- probability calibration using proper scoring rules such as Brier score and log loss;
- regime-conditional analysis and economic validation after costs, slippage, fees, financing, turnover and capacity assumptions.

The central rule is:

> **A probability estimate is not evidence of edge until its definition, uncertainty, dependence, search history, economic meaning and out-of-sample behavior are inspectable.**

No single statistic, p-value, Sharpe ratio, entropy measure, volatility model or Bayesian posterior is sufficient by itself.

## 8. Experiment classes

- **Exploratory:** hypothesis-generating; not automatically confirmatory evidence.
- **Confirmatory:** executed against a locked plan with predeclared primary tests.
- **Robustness:** tests reasonable changes in assumptions, parameters, periods, costs, universes and regimes.
- **Replication:** re-executes a claim using an independently defined dataset, period, implementation or researcher path as required.

## 9. Anti-overfitting methodology

Where appropriate, ResearchOS supports holdouts, walk-forward evaluation, purged/embargoed CV, CPCV, Probability of Backtest Overfitting diagnostics, Deflated Sharpe Ratio or equivalent adjustment, White Reality Check/Hansen SPA, multiple-hypothesis correction, parameter sensitivity, placebo/falsification tests, and benchmark/naive comparisons. No single statistic is sufficient evidence of robustness.

## 10. Research Budget and Multiple Testing Ledger

Each workspace records materially distinct hypotheses, parameterizations, datasets, model families and selection attempts contributing to a result. The ledger distinguishes planned, exploratory, failed, discarded, selected and duplicated/reproduced tests. Exploration is allowed; hidden search history is not.

## 11. Contradiction as first-class evidence

Evidence storage represents `SUPPORTING`, `CONTRADICTING`, `INCONCLUSIVE`, `FAILED_VALIDATION`, `REPLICATED`, and `NOT_REPLICATED`. Contradictory evidence remains attached to a claim even after later positive evidence.

## 12. Evidence State Machine

```text
UNTESTED → TESTED
             ├→ INCONCLUSIVE
             ├→ CONTRADICTED
             └→ CANDIDATE → ROBUSTNESS → REPLICATION → SUPPORTED
```

`REJECTED` is reserved for an explicit failed gate or declared falsification rule. Transition rules are versioned and auditable.

## 13. Evidence Independence

Repeated experiments using the same data, feature construction, period or materially identical code are not automatically independent evidence. ResearchOS should display evidence-dependence metadata.

## 14. Evidence Graph

```text
Claim
 ├── Hypothesis
 ├── Plan
 ├── Dataset versions
 ├── Experiments
 │    ├── Runs
 │    ├── Metrics
 │    └── Artifacts
 ├── Probability analyses
 │    ├── Distribution estimates
 │    ├── Conditional probabilities
 │    ├── Risk/tail estimates
 │    ├── Inference results
 │    └── Calibration results
 ├── Validation gates
 ├── Findings
 ├── Replications
 ├── Contradictions
 └── Knowledge records
```

Every derived artifact has machine-readable parent lineage.

## 15. Reproduction contract

A result is reproducible only when source data, dataset version/hash, code/version, environment/dependencies, configuration, seeds where applicable, plan version, engine version and output artifact hashes are identifiable. Status is `REPRODUCIBLE`, `PARTIALLY_REPRODUCIBLE`, or `NOT_REPRODUCIBLE`.

## 16. Knowledge promotion

Durable Knowledge is not an AI-summary cache. Promotion requires a validated Finding with complete lineage and a configured evidence threshold:

```text
Experiment → Run → Result → Validation → Finding → Knowledge
```

This preserves the existing boundary between learning and justified durable knowledge.

## 17. AI boundary

Agents may search prior research, propose hypotheses, draft plans, generate code, identify possible contradictions, suggest robustness tests, summarize evidence and explain results. Agents may not silently modify locked plans, change datasets, hide failures, promote unvalidated findings, convert uncertainty into certainty, or claim reproduction without a reproduction artifact. State-changing agent actions are logged.

## 18. Human control

High-impact transitions require explicit researcher approval unless workspace policy delegates them: locking plans, declaring primary metrics, accepting dataset transformations, promoting Findings to Knowledge and changing evidence thresholds.

## 19. Reproducible execution architecture

The execution layer should be content-addressed where practical and support immutable artifacts, append-only event history, deterministic manifests, versioned contracts, idempotent execution, retry-safe jobs, explicit failures and replay from recorded inputs.

## 20. Multi-tenant SaaS boundary

Tenant isolation is a correctness property. Tenant-owned objects need explicit ownership and authorization boundaries. The platform must support workspace isolation, RBAC, row-level authorization, immutable audit events, encrypted secrets, metering, export/deletion and disaster recovery. Shared cache/search/vector/job/artifact stores may not rely on implicit tenant context.

## 21. Version everything that can change meaning

Version data schema, dataset, feature, label, experiment, plan, validation policy, evidence-state rules, metric definition, execution engine, AI agent/prompt/tool policy and report format. Reports identify the versions that produced them.

## 22. Failure philosophy

ResearchOS fails closed for evidence integrity. If a required condition cannot be established, return explicit `UNKNOWN`/`BLOCKED` rather than silently guessing, repairing or downgrading it. Examples include unknown timestamp provenance, incomplete coverage, unverifiable hashes, missing dependency locks, failed reproduction and ambiguous train/test boundaries.

## 23. Future-proofing rule

No architecture can guarantee that future errors never occur. ResearchOS instead aims to make important errors difficult to introduce, difficult to hide, easy to detect, easy to reproduce, impossible to reinterpret silently, and recoverable without destroying historical evidence.

## 24. Product acceptance test

```text
Create Claim → Define Plan → Lock Plan → Attach Validated Dataset →
Exploratory Research → Confirmatory Experiment → Integrity Gates →
Probability / Risk / Tail Analysis → Multiple-Testing Accounting →
Out-of-Sample → Robustness → Replication → Calibration where applicable →
Supporting + Contradicting Evidence → Research Search Budget →
Missing Evidence → Evidence State → Knowledge Promotion →
Later Reproduction
```

The workflow must be executable without manually stitching files together.

## 25. Implementation order

### Phase 0 — Contract
Freeze domain contracts and invariants before UI work.

### Phase 1 — Research Claim
Implement claim identity, versioning, plan lock and lineage.

### Phase 2 — Evidence Graph
Unify experiment/run/result/validation/finding relationships into a queryable claim history, including probability-analysis artifacts.

### Phase 3 — Integrity Engine
Implement temporal integrity, provenance, reproducibility and data-quality gates.

### Phase 4 — Probability & Edge Engine
Implement deterministic probability primitives, uncertainty estimation, time-series diagnostics, tail/dependence analysis, calibration and selection-aware performance inference as composable services. No opaque single edge score.

### Phase 5 — Research Memory
Implement related-claim discovery, contradiction tracking, evidence dependence and search-budget accounting.

### Phase 6 — Replication
Implement independent replication contracts and reproducibility reports.

### Phase 7 — SaaS
Add tenant isolation, authentication, authorization, billing, metering, jobs and audit infrastructure.

### Phase 8 — AI
Add grounded research agents only after deterministic evidence and probability APIs are stable.

## 26. Core invariant

> **ResearchOS must never become more certain than its evidence.**

Every product feature, API, agent, database schema, report and UI state must preserve this invariant.
