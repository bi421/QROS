# ResearchOS — AI Context (Canonical)

This file is the compact source of truth for AI-assisted work on ResearchOS. Read it before proposing or implementing changes.

## Product target

ResearchOS is a production SaaS research platform. Local-first research remains supported, but new application work must preserve a path to multi-tenant SaaS delivery.

Scientific pipeline:

`REAL DATA → MARKET MEMORY → EXPERIMENT → EVIDENCE → CALIBRATED PROBABILITY`

Research only. No broker execution or order submission.

## Current highest-ROI work

1. Prevent false AI/manual status reports with `researchos-health` / `scripts/final_health_check.py`.
2. Prevent scope expansion and duplicate artifacts with `scripts/check_scope.py`.
3. Complete XAUUSD walk-forward validation + Bayesian probability engine.
4. Complete DXY/US10Y/VIX macro features on XAUUSD first.
5. Make out-of-sample holdout mandatory.
6. Add multiple-testing correction before accepting any edge claim.
7. Continue SaaS persistence/auth/storage/queue implementation only when it supports the product boundary.

## Mandatory evidence rule

Never report progress from an AI-generated claim alone. Before saying a task is complete, run the health check and paste the terminal output into the working session:

`researchos-health`

The output must be treated as facts. If it is not run, status is **UNVERIFIED**.

For CI, the merge gate is the combination of Python tests, C++ quant-engine job, scope guard, text-integrity guard, and final-health job.

## Scope rule

Before creating any module, script, report, or engine:

1. Search the repository for an existing implementation/name.
2. Identify the canonical owner and architecture block.
3. Reuse or extend it when possible.
4. If a new artifact is justified, record why it cannot reuse the existing one.

Do not create another `cpp_quant`/`cpp_quant_engine` tree, another `FORENSIC_AUDIT*`, or another `run_full_analysis*.py` family without an explicit architecture decision.

Scratch/test artifacts belong under `scratch/` or `archive/`; do not leave one-off dumps at repository root.

## Scientific rules

- XAUUSD is the first and current macro-integration asset.
- DXY, US10Y, and VIX must be validated without interpolation, forward-fill, resampling, or synthetic repair unless a future contract explicitly permits it.
- Walk-forward validation is mandatory; in-sample-only evidence cannot pass a research gate.
- Out-of-sample holdout is mandatory, not optional.
- Multiple-testing correction is mandatory before accepting a discovered edge.
- Bayesian probability must preserve provenance, calibration evidence, and uncertainty; it must not turn weak evidence into certainty.
- Never claim a profitable edge from an inconclusive or failed gate.

## Encoding / reproducibility rules

All repository text is UTF-8 without BOM. Pre-commit and CI enforce BOM/trailing-whitespace checks.

Percentage semantics are explicit: values named `*_pct` are percentages, while fractional returns/probabilities remain in `[0, 1]` form where their contract says so. Existing Python/C++ percentage-return tests are canonical; do not add duplicate implementations.

## Architecture rule

Every new engine or capability must state which existing architecture block it belongs to and how it crosses the scientific core boundary. Do not create parallel cores, runners, or adapters merely to rename existing functionality.

## Documentation rule

Current decisions and status belong in canonical docs. Historical audits and reports are evidence, not active architecture. Preserve useful historical material under `archive/reports/YYYY-MM/` when cleanup is performed; do not let stale reports become competing sources of truth.

## Review rule

AI is an implementation assistant, not an authority. Claude/ChatGPT output must be treated as a proposal until repository tests, deterministic health checks, and scientific gates confirm it.

A weekly critique pass should ask: what architectural weakness remains, what simpler design exists, and what evidence would falsify the current design?
