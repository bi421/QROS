# ResearchOS SaaS Product Implementation Plan

**Status:** Active implementation contract
**Target:** Production SaaS, not a demo/dashboard wrapper
**Scientific boundary:** `researchos.research_core`

## Product promise

> AI proposes. ResearchOS tests. Evidence decides.

The SaaS product will let an authenticated user upload a compatible dataset, define a research request, run the frozen scientific workflow asynchronously, and retrieve an auditable result. It will never claim profitability merely because a run completed.

## Production architecture

```text
Browser / API client
        |
        v
Identity provider (Supabase Auth)
        |
        v
ResearchOS API
  |      |       |
  |      |       +--> Usage / plan policy
  |      +----------> Tenant authorization
  +-----------------> Job creation
        |
        v
Postgres / Supabase
  workspace
    -> membership
    -> dataset
       -> dataset_version
    -> research_run
       -> artifact
          -> evidence
        |
        v
Worker queue
        |
        v
ResearchOS scientific core
        |
        v
Content-addressed artifacts + evidence
        |
        v
API / report / dashboard
```

## Required product capabilities

### P0 — Product foundation

- authenticated accounts;
- workspaces/tenants;
- workspace membership and roles;
- fail-closed authorization;
- dataset upload and immutable dataset versions;
- asynchronous research jobs;
- job state machine and retry policy;
- artifact/evidence persistence;
- usage metering;
- plan enforcement;
- API versioning;
- audit log;
- health/readiness endpoints;
- structured error contract;
- request correlation IDs;
- rate limiting;
- secret-free browser clients.

### P1 — User product

- web application shell;
- sign-in/sign-out/account recovery;
- workspace switcher;
- dataset library;
- research run form;
- live job status;
- evidence result page;
- provenance/audit page;
- report export;
- API keys for programmatic research;
- usage/billing page.

### P2 — Commercialization

- Stripe subscription lifecycle;
- checkout/customer portal;
- webhook signature verification;
- plan entitlements sourced from server-side subscription state;
- invoice/payment failure handling;
- trial limits;
- enterprise workspace controls.

### P3 — AI research agent

- natural-language hypothesis intake;
- structured experiment specification;
- tool calls only through the ResearchOS application boundary;
- evidence-grounded result explanation;
- explicit `PROVEN`, `REJECTED`, and `INCONCLUSIVE` states;
- no LLM-generated statistics accepted as scientific evidence;
- every AI claim linked to persisted evidence or marked as unverified.

## Non-negotiable boundaries

1. Scientific calculations stay outside the SaaS layer.
2. No tenant identifier is accepted as an authorization claim from the request body.
3. Every tenant-owned database row carries workspace ownership and is protected by database policy.
4. Browser code never receives privileged database/service credentials.
5. Research execution is asynchronous.
6. Dataset bytes and derived artifacts remain content-addressed.
7. Billing state is authoritative on the server/database, not the browser.
8. A completed job is not evidence of a positive edge.
9. CI green is software evidence only, not scientific evidence.
10. Local mode remains functional without SaaS authentication or network access.

## Definition of done for SaaS MVP

The MVP is not complete until all of the following are true:

- a new user can authenticate;
- a user can create/join a workspace;
- two workspaces cannot read each other's datasets, jobs, or artifacts;
- a user can upload a compatible XAUUSD M1 dataset;
- the dataset receives immutable provenance;
- a research run is queued and executed by a worker;
- the worker invokes the existing scientific core rather than a second implementation;
- result artifacts are persisted and retrievable;
- source-to-result audit passes;
- usage limits are enforced server-side;
- subscription entitlements are enforced server-side;
- the application has no hard-coded credentials;
- API and UI have automated tests;
- tenant-isolation tests exist;
- deployment health/readiness checks exist;
- production observability exists;
- CI is green on the release candidate;
- a real end-to-end staging run has been completed.

## Implementation sequence

1. SaaS contracts and fail-closed API boundary.
2. Persistent Postgres/Supabase schema + RLS.
3. Supabase authentication adapter.
4. Dataset upload/storage boundary.
5. Durable research-job queue/worker.
6. Artifact/evidence persistence.
7. Usage metering and entitlements.
8. Web application.
9. Billing/subscriptions.
10. AI research agent.
11. Staging end-to-end test.
12. Production hardening and release.

No later layer may bypass an earlier security or scientific boundary.
