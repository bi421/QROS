# ResearchOS SaaS Differentiation Audit

**Date:** 2026-09-17  
**Base:** `main` at `ab0390f0d819297ec7613074e4068f915566700e`  
**Purpose:** Determine whether ResearchOS has a defensible product distinction before expanding SaaS infrastructure.

## Executive finding

ResearchOS does **not** currently have a sufficiently explicit product-level differentiator.

The repository already contains unusually strong building blocks around deterministic computation, evidence, experiment lineage, reproduction, validation, learning, and durable Knowledge. Those capabilities are real architectural assets, but they are not yet packaged into one clear user-facing product loop.

The current README positions ResearchOS as an "Institutional-Grade Market Research Platform" and emphasizes determinism, explainability, scientific rigor, and no trading. That positioning is credible but broad. It does not by itself distinguish ResearchOS from mature quantitative research platforms. The repository also already contains experiment learning and durable Knowledge concepts, so simply adding "research memory" would not be sufficient differentiation unless it becomes a concrete workflow and product primitive. 

## Competitive reality checked 2026-09-17

### QuantConnect

QuantConnect already covers research, backtesting, optimization, statistical validation, realistic modeling, out-of-sample paper trading, live deployment, and an AI assistant. Its current product explicitly describes ideas moving through a gated research-to-production pipeline and centralized tracking of multiple ideas. Therefore, "AI quant research", "research pipeline", "evidence gates", "backtesting", and "optimization" are not sufficient differentiators by themselves.

Source: https://www.quantconnect.com/

### TradingView

TradingView already provides strategy reports, historical backtesting, forward testing, trade-level analysis, deep backtesting, bar replay, and paper trading. Therefore, chart-based strategy testing, historical validation, and paper/forward testing are commodity capabilities at product level.

Sources:
- https://www.tradingview.com/support/solutions/43000754966-demo-features-on-tradingview/
- https://www.tradingview.com/support/solutions/43000562362-what-are-strategies-backtesting-and-forward-testing/
- https://www.tradingview.com/support/solutions/43000666265-how-deep-backtesting-works/

### MLflow / general experiment tracking

MLflow already provides experiment/run tracking, parameters, metrics, artifacts, dataset tracking, comparison, and reproducibility. Therefore, generic "experiment tracking" or "experiment history" is also not enough.

Source: https://mlflow.org/docs/latest/ml/tracking

## What ResearchOS already has

Repository inspection found:

- Evidence emission and an EvidenceRepository.
- Experiment → Run → Result → Validation → Finding → Knowledge concepts.
- Reproduction with preserved validation lineage.
- A lineage query test surface.
- Experiment-level LearningRecord that captures what an experiment taught.
- Durable `Knowledge` as the canonical semantic memory object.
- An explicit architectural invariant that LearningRecord must not bypass validated evidence when promoted into durable Knowledge.

These are meaningful foundations. They are not yet a differentiated SaaS proposition by themselves.

## Candidate differentiation

The strongest candidate is **Evidence Memory / Research Memory with provenance-aware novelty and contradiction detection**.

The product would not merely store experiments. It would answer questions such as:

1. Have I already tested this hypothesis or a materially equivalent one?
2. Which previous experiments support, contradict, or qualify this claim?
3. Which failures are relevant to the current hypothesis?
4. Is the current positive result genuinely new evidence or a near-duplicate of prior work?
5. Which dataset, code version, parameter family, regime, and validation path produced each result?
6. Has the claim been independently replicated?
7. What evidence is still missing before this claim can be promoted to durable Knowledge?

This is stronger than generic experiment tracking because the unit of product value is not a run. It is the **claim and its accumulated evidence history**.

## Required product primitive

Introduce a user-facing concept tentatively named `Research Claim`:

```text
CLAIM
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

The system should preserve both positive and negative evidence. A failed experiment is not disposable output; it becomes part of the claim's evidence history.

## Product differentiation test

ResearchOS should not claim differentiation until the following workflow can be demonstrated end-to-end:

```text
User enters a research claim
        ↓
ResearchOS finds related prior claims
        ↓
System explains similarity and prior outcomes
        ↓
User runs a new experiment
        ↓
Validation produces structured evidence
        ↓
System updates the claim's evidence history
        ↓
System identifies support / contradiction / uncertainty
        ↓
System states what evidence is still missing
        ↓
Only validated findings can become durable Knowledge
```

## What we should NOT build as the differentiator

- Another generic backtesting dashboard.
- Another AI strategy generator.
- Broker execution.
- Generic experiment logging.
- A simple chat wrapper around the existing engine.
- A generic trading signal marketplace.
- A feature checklist copied from existing platforms.

## Product thesis

> **ResearchOS is an evidence operating system for quantitative research: it remembers every research claim, connects each claim to its experiments and validation evidence, preserves failed and contradictory results, and shows what is actually justified by the accumulated evidence.**

This thesis must be proven in product behavior before it is treated as a marketing claim.

## Next implementation order

1. Freeze the current quantitative engine and avoid unrelated refactors.
2. Define `Research Claim`, evidence states, and lineage contracts.
3. Map the existing Experiment / Finding / Knowledge implementation to those concepts.
4. Implement prior-claim retrieval and related-claim matching without changing scientific results.
5. Implement claim-level evidence aggregation including negative and contradictory evidence.
6. Implement replication and contradiction records.
7. Build a minimal UI around the claim → evidence history workflow.
8. Only after the core loop works, add SaaS tenancy, authentication, billing, collaboration, and AI assistance.

## Decision gate

The SaaS architecture should proceed only after the claim/evidence-memory loop has a reproducible test demonstrating that a user can answer:

> **"What do I already know about this claim, why do I believe it, what contradicts it, and what evidence is still missing?"**

If the system cannot answer that question from its own stored lineage, the proposed differentiation is not yet implemented.
