# QROS Solo-Founder Fast Track

## Purpose

Reduce QROS to the smallest evidence-first XAUUSD research product that one maintainer can operate, verify, support, and sell. This plan changes delivery scope, not existing scientific calculations or safety boundaries.

## Operating rules

1. **One active delivery objective at a time.** Do not start another engine while the current objective lacks an end-to-end proof.
2. **Additive changes only.** Preserve established calculation contracts unless a separately reviewed bug fix proves a change is required.
3. **No feature without a user-facing acceptance test.** A module, interface, or green unit-test suite alone does not complete a product capability.
4. **Evidence over status language.** Record exact main SHA, required check conclusions, test commands/results, integration evidence, and external dependencies.
5. **No silent fallback.** Missing, stale, invalid, or uncalibrated inputs must produce an explicit blocked/insufficient-evidence state, not a fabricated probability.
6. **No order execution.** QROS is research and decision-support software; it must not place trades.
7. **Prefer managed services and the simplest deployable design.** Do not build infrastructure, abstraction layers, or performance optimizations without a demonstrated requirement.
8. **Keep a strict work-in-progress limit of one.** Merge only verified work; then re-read the actual main SHA before selecting the next task.

## Product boundary for the first sellable release

The first release is a narrowly scoped XAUUSD research workflow, not the full envisioned research operating system.

A user must be able to:
- access an authenticated workspace with explicit entitlement;
- select or upload a supported XAUUSD dataset with documented schema and time zone;
- run one canonical, versioned research configuration;
- receive a durable, reproducible report/evidence artifact with dataset hash, model/code version, assumptions, sample counts, costs, and validation status;
- distinguish descriptive/backtest results from out-of-sample calibrated probabilities and from unproven claims;
- retrieve the same completed run and its evidence without recomputing or changing its identity.

Initial release constraints:
- XAUUSD only.
- One documented data contract and one canonical research path.
- A small, fixed set of timeframes/configurations only where current code already supports them.
- No live-feed requirement for the first release unless a complete historical/replay path has already been proven.
- No automated execution, broker orders, or claims of guaranteed profitability.
- No self-service team/billing complexity unless needed to onboard the first paying customer; manual founder-led onboarding is acceptable for the pilot.

## Delivery gates

### Gate 1 — Freeze scope and choose one canonical path
- Inventory what is implemented, tested, integrated, and externally dependent.
- Name one API/CLI entry point, one input contract, one run contract, and one evidence output.
- Mark speculative, duplicate, unintegrated, and non-release modules as deferred; do not delete them as part of this scope change.
- Acceptance: a new contributor can follow one documented sequence from input to output without guessing which engine is canonical.

### Gate 2 — Prove one end-to-end research run
- Use a pinned, licensed/approved XAUUSD dataset and immutable dataset fingerprint.
- Validate timestamp ordering, duplicates, gaps, OHLC constraints, timezone/session assumptions, and outcome-label construction.
- Run the existing research path without changing its math.
- Persist the run state and evidence artifact; verify retrieval and reproducibility.
- Acceptance: a clean environment can execute the documented command/API path and retrieve an artifact tied to the exact input and code versions.

### Gate 3 — Validate claims, not just code
- Establish a simple baseline and compare the current method against it.
- Use chronological out-of-sample splits; prevent future-data leakage.
- Report sample size, class balance, TP-before-SL label policy, spread/commission/slippage assumptions, uncertainty, and calibration where applicable.
- Keep a probability marked uncalibrated unless the applicable OOS calibration gate passes.
- Acceptance: report includes both positive and negative/insufficient-evidence outcomes and does not imply profitability from a successful test suite.

### Gate 4 — Minimum reliable pilot deployment
- Deploy one documented environment with HTTPS and a tested health check.
- Verify authentication, workspace/tenant isolation, entitlement denial, job failure/retry behavior, and durable result retrieval.
- Configure backup credentials and perform a restore test; document measured RPO/RTO instead of assuming them.
- Add only the minimum logs/alerts needed for a solo maintainer to detect failed runs, storage/queue issues, and service downtime.
- Acceptance: one external pilot user can complete the canonical workflow without manual database intervention, and the founder can diagnose and recover a failed run.

### Gate 5 — First customer before platform expansion
- Onboard one real pilot customer manually if necessary.
- Observe whether the workflow solves a concrete research problem and whether the customer will pay.
- Fix only blockers, correctness defects, security issues, and directly observed usability failures.
- Defer broad integrations, additional instruments, advanced team features, and optimizations until usage or measured profiling justifies them.

## Explicitly deferred unless required by a proven blocker

- Additional general-purpose quant engines and duplicate probability abstractions.
- Live multi-provider market-state reconstruction and venue-specific reconnect/reset semantics.
- C++ optimization not supported by profiling evidence.
- More instruments, strategy families, indicators, or dashboards.
- Full self-service organization management, complex billing, and enterprise features.
- Claims of production disaster recovery before a restore has actually been tested.
- Any model or feature that lacks a clear acceptance test in the canonical product path.

## Definition of done for every PR

A PR is complete only when:
- its purpose is tied to one delivery gate;
- its change is additive or a reviewed correctness fix;
- targeted tests and required repository checks pass on the exact PR head SHA;
- no required check is pending, skipped, or silently bypassed;
- the integration boundary is explicit;
- the corresponding end-to-end evidence is updated where the user-facing behavior changes;
- the change is merged under repository protection and the resulting main SHA is re-verified.

A green CI run proves only the checks that ran. It does not by itself prove live data integration, calibrated probabilities, production deployment, tenant isolation, backup restoration, or commercial value.

## Solo-founder weekly operating cadence

1. Pick the single highest-risk unmet release gate.
2. Define one observable acceptance test before editing code.
3. Implement the smallest additive change.
4. Run focused tests, then required CI on the exact SHA.
5. Merge only after required checks pass.
6. Verify the new main SHA and record evidence/dependencies.
7. Stop feature work when the gate passes; move to the next unmet gate.

## Current release blockers to verify against live repository state

Treat the following as unproven until current exact-SHA or environment evidence is recorded:
- one canonical XAUUSD run from raw/pinned input through durable evidence retrieval;
- chronological OOS evaluation and appropriately qualified calibration;
- live provider/worker wiring for market-state sequence checks;
- staging HTTPS, authentication and tenant-isolation smoke tests;
- configured backup credentials and a successful restore drill;
- first external pilot user and willingness to pay.

This document is a scope and acceptance contract, not evidence that any of these gates has already passed.
