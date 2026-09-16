# ResearchOS SaaS — Product Constitution

**Status:** Draft 0.1 — differentiation-first  
**Date:** 2026-09-17

## 1. Product thesis

ResearchOS is an evidence operating system for quantitative research.

It is not primarily a backtesting tool, signal generator, broker, or strategy marketplace.

Its core job is to help a researcher determine what a research claim is actually supported by accumulated, reproducible evidence.

## 2. The problem

Quantitative researchers can already generate backtests, optimize parameters, compare runs, and track experiments with existing products.

The harder problem is research memory:

- Have I tested this claim before?
- Which prior results support it?
- Which results contradict it?
- Which failed experiments are relevant?
- Is this result genuinely new evidence?
- Can I reproduce the result from the recorded lineage?
- Has the claim survived independent replication?
- What evidence is still missing?

ResearchOS exists to answer those questions from structured research history.

## 3. Core differentiated primitive: Research Claim

A Research Claim is the durable object around which research history is organized.

```text
RESEARCH CLAIM
      ↓
HYPOTHESIS
      ↓
EXPERIMENTS
      ↓
RUNS
      ↓
VALIDATION
      ↓
FINDINGS
      ↓
EVIDENCE MEMORY
      ↓
REPLICATION / CONTRADICTION
      ↓
KNOWLEDGE STATUS
```

A run is an execution. A claim is the thing the researcher is trying to establish or falsify.

## 4. Evidence Memory

ResearchOS must preserve the complete evidence history of a claim, including:

- supporting evidence;
- negative evidence;
- contradictory evidence;
- inconclusive results;
- validation failures;
- replication attempts;
- dataset identity and version;
- code/version lineage;
- parameter/configuration lineage;
- regime/context metadata;
- provenance and reproducibility information.

Failed research is not garbage. It is part of the memory of the claim.

## 5. User-visible product promise

The product should eventually answer, with inspectable evidence:

> What do I already know about this claim, why do I believe it, what contradicts it, and what evidence is still missing?

The system must never turn an unsupported claim into a positive conclusion merely because a backtest produced a favorable metric.

## 6. Evidence states

The initial product vocabulary is:

- `SUPPORTED` — evidence satisfies the configured validation requirements.
- `CONTRADICTED` — relevant evidence materially conflicts with the claim.
- `INCONCLUSIVE` — evidence exists but does not justify a supported/contradicted state.
- `UNTESTED` — insufficient empirical evidence exists.
- `REJECTED` — a configured validation gate explicitly rejects the claim.

These are evidence states, not trading recommendations.

## 7. Scientific boundary

ResearchOS must preserve the existing principles:

- deterministic computation;
- reproducibility;
- falsifiable hypotheses;
- explicit provenance;
- validation before durable knowledge;
- no broker execution;
- no guaranteed-profit claims;
- no hidden synthetic data repair;
- no bypass around evidence gates.

## 8. Existing architecture to reuse

The repository already contains important foundations:

- EvidenceRepository and evidence emission;
- experiment/run/result/validation/finding lineage;
- reproduction and lineage reporting;
- experiment LearningRecord;
- durable Knowledge memory;
- explicit protection against promoting unvalidated learning into durable Knowledge.

The SaaS product must compose these capabilities instead of creating parallel abstractions without a concrete responsibility.

## 9. What is NOT differentiation

The following are capabilities, not the core moat:

- AI chat;
- generic backtesting;
- parameter optimization;
- dashboards;
- experiment tracking alone;
- cloud compute;
- broker integrations;
- strategy generation;
- paper trading;
- generic authentication/billing.

Other mature products already provide substantial parts of these capabilities.

## 10. Product loop

```text
CLAIM
  ↓
DISCOVER PRIOR RESEARCH
  ↓
FORMALIZE HYPOTHESIS
  ↓
RUN EXPERIMENT
  ↓
VALIDATE
  ↓
UPDATE EVIDENCE MEMORY
  ↓
CHECK SUPPORT / CONTRADICTION / REPLICATION
  ↓
IDENTIFY MISSING EVIDENCE
  ↓
PROMOTE ONLY VALIDATED FINDINGS TO KNOWLEDGE
```

## 11. MVP

The first SaaS MVP is intentionally small.

### Claim workspace

A user creates a research claim and sees its complete evidence history.

### Related research

ResearchOS identifies previous claims/experiments that are materially related to the current claim.

### Evidence timeline

Every result is connected to its dataset, experiment, validation, finding, and source lineage.

### Contradiction view

The user can see evidence that supports and conflicts with the claim rather than only the best result.

### Missing-evidence checklist

The system identifies which configured validation or replication requirements remain incomplete.

### Knowledge promotion gate

Only a validated finding can be promoted into durable Knowledge.

## 12. Anti-self-deception objective

A central design objective is to make selective research memory difficult.

If a researcher runs 100 experiments and 3 are positive, the system should not present only the 3 positive results as the research history.

The claim history must retain the negative and inconclusive evidence and make the selection visible.

## 13. Competitive position

ResearchOS should not attempt to win by being a broader trading platform than established products.

It should occupy a narrower category:

> **Evidence memory and claim validation for quantitative research.**

The product must earn this position through actual workflow behavior, not marketing language.

## 14. SaaS architecture sequence

Do not build the full SaaS stack first.

### Phase A — Product primitive

1. Claim contract.
2. Claim-to-hypothesis linkage.
3. Claim-to-experiment lineage.
4. Evidence aggregation.
5. Contradiction detection contract.
6. Replication contract.
7. Missing-evidence contract.

### Phase B — Minimal product

1. Claim creation.
2. Claim history.
3. Related research.
4. Evidence timeline.
5. Validation state.
6. Knowledge promotion.

### Phase C — SaaS foundation

1. Supabase/Postgres tenancy model.
2. Authentication.
3. Workspace/project isolation.
4. API authorization.
5. Usage metering.
6. Billing.
7. Audit logs.
8. Background jobs.

### Phase D — Intelligence

1. Semantic claim matching.
2. Research duplication detection.
3. Contradiction discovery.
4. Evidence-gap recommendations.
5. Natural-language research assistant.

AI is an interface and accelerator. It is not the source of truth.

## 15. Non-goals

ResearchOS will not:

- execute live trades;
- claim guaranteed profitability;
- sell unverified trading signals as facts;
- hide failed experiments;
- silently repair missing market data;
- replace empirical validation with an LLM opinion;
- treat a single positive backtest as proof of an edge.

## 16. Differentiation acceptance test

The product is not considered differentiated until an end-to-end test demonstrates:

1. Create claim `C1`.
2. Run multiple experiments against `C1`.
3. Store positive, negative, and inconclusive outcomes.
4. Create a second materially similar claim `C2`.
5. Retrieve the relevant prior evidence automatically.
6. Explain which evidence supports or contradicts the new claim.
7. Preserve reproducible lineage for every conclusion.
8. Identify missing validation/replication evidence.
9. Prevent unvalidated findings from becoming durable Knowledge.

The test must be automated and reproducible.

## 17. Success metric

The primary product metric is not number of backtests.

It is:

> **Percentage of research claims for which ResearchOS can reconstruct the relevant prior evidence, contradictions, provenance, and remaining evidence gaps without manual reconstruction.**

## 18. Immediate implementation rule

Until the differentiation acceptance test exists:

- do not add unrelated SaaS features;
- do not redesign the C++ engine;
- do not add broker execution;
- do not add generic AI features;
- do not declare the SaaS architecture complete.

The next engineering milestone is the smallest production-quality implementation of the Research Claim + Evidence Memory loop.
