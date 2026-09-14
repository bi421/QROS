# ResearchOS SaaS Architecture Boundary

**Status:** Active production architecture contract
**Scope:** Local ResearchOS + production SaaS
**Scientific baseline:** `docs/M1_RESEARCH_BASELINE_FREEZE_2026-09.md`
**Implementation contract:** `docs/saas/PRODUCT_IMPLEMENTATION_PLAN.md`

## 1. Product boundary

ResearchOS supports two delivery modes over the same scientific core:

```text
                         ResearchOS Core
                              |
                +-------------+-------------+
                |                           |
           Local Mode                  SaaS Mode
                |                           |
             CLI/API                    Web/API
                |                           |
          local storage             Auth + Postgres
                                          + queue
                                          + object storage
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

The application/API layer owns:

- authentication and authorization;
- workspace and tenant isolation;
- dataset upload orchestration;
- research-job creation;
- job state transitions;
- result retrieval;
- usage limits;
- subscription entitlements;
- report delivery;
- API request validation;
- rate limiting and request correlation.

The application layer must call the core rather than duplicate scientific calculations.

## 4. Persistence responsibilities

Production persistence separates:

```text
workspace
  -> membership
  -> subscription
  -> dataset
      -> dataset_version
  -> research_run
      -> artifact
          -> evidence
  -> audit_event
```

Every tenant-owned resource is bound to a workspace. Cross-workspace reads and writes must fail closed at both application and database policy layers.

## 5. Research job boundary

Long-running research must not execute synchronously inside an HTTP request.

```text
API request
    -> authorize workspace
    -> validate entitlement
    -> create research_run
    -> QUEUED
    -> durable worker queue
    -> RUNNING
    -> ResearchOS Core
    -> artifact/evidence persistence
    -> SUCCEEDED or FAILED
```

The job state machine is:

`QUEUED -> RUNNING -> SUCCEEDED`

with terminal failure/cancellation states:

`RUNNING -> FAILED`

`QUEUED/RUNNING -> CANCELLED`

State transitions must be monotonic and authorization-scoped.

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

## 7. Security rules

- Authentication is delegated to a supported identity provider; the default API behavior is fail-closed.
- Authorization is workspace-based, not merely “authenticated user” based.
- Database RLS is defense in depth for tenant isolation.
- Service-role/secret credentials never reach browser clients.
- Subscription state is server authoritative.
- API keys are stored only as hashes and are shown once at creation.
- Rate limits are enforced server-side.
- Audit events never contain secrets or raw authentication tokens.

## 8. Local mode requirement

Local users retain a complete research path without SaaS authentication, subscriptions, or network connectivity for core computation.

Local mode is a first-class supported delivery mode, not a debug-only mode.

## 9. Initial SaaS MVP boundary

The first SaaS product exposes one frozen research workflow:

```text
Authenticate
    -> create workspace
    -> upload compatible XAUUSD M1 data
    -> validate immutable dataset version
    -> queue frozen research pipeline
    -> persist auditable artifacts/evidence
    -> display report
```

Do not add broker execution or unvalidated predictive products to the MVP.

## 10. AI boundary

The AI layer is an application-level research agent. It may:

- translate natural-language hypotheses into structured requests;
- call approved ResearchOS tools;
- explain persisted evidence;
- identify failed gates and request follow-up experiments.

It may not:

- fabricate statistics;
- alter scientific artifacts;
- bypass validation gates;
- authorize itself;
- access another workspace;
- convert an `INCONCLUSIVE` or failed result into a positive claim.

## 11. Implementation rule

SaaS work follows this order:

1. preserve/freeze scientific behavior;
2. define narrow application contracts;
3. add interface and tenant-isolation tests;
4. implement durable persistence and authorization;
5. implement queue/worker execution;
6. implement web delivery;
7. implement billing and entitlements;
8. implement the AI research agent;
9. verify local mode remains functional;
10. run full CI and staging end-to-end validation before release.
