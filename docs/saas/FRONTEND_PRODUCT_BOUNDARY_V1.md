# QROS Browser Product Boundary V1

Status: **implementation-ready boundary; framework-neutral**.

This document does not select React, Next.js, Svelte, or another frontend
framework. It defines the browser/application contract that any future frontend
must implement without changing SaaS authorization or scientific contracts.

## Browser trust boundary

The browser may hold:
- publishable/client authentication state;
- short-lived user session material managed by the chosen auth integration;
- non-sensitive API response data.

The browser must never hold:
- Supabase service-role credentials;
- database passwords;
- recovery credentials;
- billing webhook secrets;
- worker credentials.

All tenant identity and authorization decisions come from the authenticated
server-side TenantContext.

## Screen / route boundary

| Surface | Required API boundary | Required states |
|---|---|---|
| Sign in / recovery | Supabase Auth integration | loading, invalid credentials, recovery pending, success |
| Workspace shell | `GET /v1/me` | loading, authenticated, no workspace, multi-workspace selection, error |
| Dataset library | `POST /v1/datasets`, dataset version list | upload progress, empty, success, validation error, size-limit error |
| Dataset version detail | dataset version read boundary | loading, immutable metadata, not found |
| Research request | `POST /v1/research-runs` | plan/entitlement check, validation error, idempotent submission |
| Run status | `GET /v1/research-runs/{job_id}` | queued, running, succeeded, failed, cancelled, timeout/retry |
| Result | `GET /v1/research-runs/{job_id}/result` | loading, immutable result, unavailable |
| Evidence | `GET /v1/research-runs/{job_id}/evidence` | empty, lineage list, loading, forbidden/not found |
| Claim / plan | claim create/read + plan-lock route | draft, locked, conflict, validation failure |
| Validation / finding | validation/finding routes | pending, validated, rejected/inconclusive, lineage error |
| Report | `GET /v1/research-runs/{job_id}/report` | generating, available, unavailable |
| Audit | audit-event read boundary when exposed | empty, paginated, filtered, error |
| Usage / billing | server-side subscription/entitlement projection | active, trialing, exhausted, payment-required, unavailable |

## Research workflow

The UI should expose the governed sequence:

`Workspace → Dataset → Claim → Plan Lock → Research Run → Result →
Validation → Finding → Evidence/Report`.

The UI must not invent a parallel scientific workflow or write evidence state
directly.

## Tenant isolation

The frontend must treat resource IDs as opaque identifiers. It must never:
- select a workspace by putting an arbitrary workspace ID into a request body;
- infer authorization from client metadata;
- cache one workspace's resources into another workspace's view;
- display a resource after a 404/authorization boundary says it is not visible.

Workspace changes must invalidate tenant-scoped client caches.

## Error contract

The UI should preserve:
- HTTP status;
- stable `code`;
- `message`;
- `request_id`;
- `correlation_id`.

Do not display internal exception text or secrets. Request IDs should be
available to the user for support/debugging.

## Loading / empty / failure rules

Every remote surface requires explicit:
1. loading state;
2. empty state;
3. success state;
4. recoverable error state;
5. authorization/not-found state where applicable.

A failed research run is a durable terminal state, not a loading state.

## Billing / usage boundary

The UI may display server-provided plan and entitlement state. It must not
calculate or authorize usage locally. A 402/429 response is authoritative for
the corresponding server-side limit.

## Implementation handoff

The remaining product decision is the frontend technology/deployment architecture.
Once selected, implementation can map these boundaries directly to the existing
API contract without changing the SaaS domain model.
