# ResearchOS SaaS Architecture Boundary

**Status:** Phase 1 architecture contract
**Scope:** Local ResearchOS + future SaaS
**Scientific baseline:** `docs/M1_RESEARCH_BASELINE_FREEZE_2026-09.md`

## 1. Product boundary

ResearchOS will support two delivery modes over the same scientific core:

```text
                         ResearchOS Core
                              |
                +-------------+-------------+
                |                           |
           Local Mode                  SaaS Mode
                |                           |
             CLI/API                    Web/API
                |                           |
          local storage             database/storage
```

The scientific core is the source of truth for research computation. SaaS infrastructure must not redefine scientific semantics.

## 2. Core responsibilities

The core owns:

- dataset validation and deterministic transformation;
- market-memory construction;
- experiment execution;
- quantitative evaluation;
- walk-forward temporal rules;
- outcome semantics;
- calibration;
- evidence construction;
- provenance and SHA-256 identity binding;
- negative controls;
- scientific audit invariants.

The core must not depend on:

- HTTP requests;
- browser/UI code;
- authentication providers;
- user accounts;
- subscription state;
- payment providers;
- SaaS tenant identifiers;
- deployment-specific secrets.

## 3. Application responsibilities

The application/API layer will own:

- authentication and authorization;
- workspace and tenant isolation;
- dataset upload orchestration;
- research-job creation;
- job state transitions;
- result retrieval;
- usage limits;
- report delivery;
- API request validation.

The application layer must call the core rather than duplicate scientific calculations.

## 4. Persistence responsibilities

Persistent storage will eventually separate:

```text
workspace
  -> dataset
      -> dataset_version
  -> experiment
      -> experiment_run
          -> artifact
              -> evidence
```

Every tenant-owned resource must be bound to a workspace. Cross-workspace reads must fail closed.

## 5. Research job boundary

Long-running research must not execute synchronously inside an HTTP request.

Target flow:

```text
API request
    -> create research_run
    -> QUEUED
    -> worker
    -> ResearchOS Core
    -> artifact/evidence persistence
    -> SUCCEEDED or FAILED
```

The job state machine is:

`QUEUED -> RUNNING -> SUCCEEDED`

with terminal failure/cancellation states:

`RUNNING -> FAILED`

`QUEUED/RUNNING -> CANCELLED`

## 6. Scientific integrity rules

SaaS features must preserve the frozen research invariants:

- source artifacts remain SHA-256 bound;
- source/result contracts remain identical;
- temporal ordering remains leakage-safe;
- OOS validation windows are not reused;
- calibration uses only eligible prior observations;
- negative controls remain available;
- evidence provenance remains auditable;
- no broker execution is introduced;
- no predictive-edge or profitability claim is introduced without separate validation.

A SaaS convenience feature is not allowed to weaken a scientific invariant.

## 7. Local mode requirement

Local users must retain a complete research path without requiring SaaS authentication, subscriptions, or network connectivity for core computation.

Local mode therefore remains a first-class supported delivery mode, not a debug-only mode.

## 8. Initial SaaS MVP boundary

The first SaaS product will expose only one frozen research workflow:

```text
Upload validated-compatible XAUUSD M1 data
    -> validate dataset
    -> run frozen research pipeline
    -> produce auditable evidence/report
```

Do not add multiple assets, autonomous trading, broker execution, or unvalidated predictive products to the first MVP.

## 9. Implementation rule

Future SaaS work must follow this order:

1. preserve/freeze scientific behavior;
2. define a narrow interface;
3. add tests at the interface boundary;
4. implement persistence/orchestration around the interface;
5. verify local mode remains functional;
6. verify SaaS tenant isolation;
7. run full CI before merge.

This document is an architecture boundary, not a claim that the SaaS implementation already exists.
