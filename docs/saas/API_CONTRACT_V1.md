# QROS SaaS API Contract v1

**Status:** Active contract  
**Version:** v1  
**Scope:** HTTP application boundary only  
**Scientific authority:** `researchos.research_core`

## 1. Contract invariants

- Authentication and workspace authorization are mandatory for tenant-owned endpoints.
- A workspace identifier supplied by a client is never trusted as an authorization claim.
- Tenant ownership is resolved from the authenticated `TenantContext`.
- Scientific calculations are performed by the ResearchOS core, not the HTTP layer.
- Dataset versions are immutable and identified by SHA-256 content identity.
- Research runs execute asynchronously.
- A completed run is not, by itself, evidence of a positive research finding.

Research reports are presentation projections only. They preserve the governed result status, source dataset hash, result manifest hash, artifact hashes, and stored evidence lineage. They must not infer causality, profitability, significance, or a positive finding.
- Browser clients never receive Supabase service-role credentials.
- All mutating operations must be idempotent before production launch.
- Cross-workspace access must fail closed.

## 2. Versioning

The public API namespace is `/v1`.

Breaking changes require a new major API namespace. Additive response fields may be introduced only when existing clients remain valid.

## 3. Authentication

Tenant endpoints authenticate through the configured `AuthProvider`.

The default provider is fail-closed and returns HTTP 503 until a production identity provider is configured.

The authenticated context contains:

- `user_id`
- `workspace_id`
- `plan`
- `role` — server-authoritative workspace membership role.

## 4. Endpoints

### System

- `GET /healthz` — process health.
- `GET /readyz` — dependency/readiness boundary.

### Identity

- `GET /v1/me` — returns the authenticated user, workspace, and effective plan.

### Datasets

- `POST /v1/datasets` — create a dataset and immutable version from an upload.
- `POST /v1/datasets/{dataset_id}/versions` — append an immutable dataset version.
- `GET /v1/datasets/{dataset_id}/versions` — list versions visible to the authenticated workspace.

Dataset bytes are streamed through a bounded SHA-256 calculation before persistence. Storage paths are tenant-scoped and content-addressed.

### Research

- `POST /v1/research-runs` — enqueue a frozen research workflow.
- `GET /v1/research-runs/{job_id}` — retrieve a workspace-scoped job.
- `GET /v1/research-runs/{job_id}/result` — retrieve the immutable governed result projection.
- `GET /v1/research-runs/{job_id}/evidence` — retrieve tenant-scoped stored evidence lineage.
- `GET /v1/research-runs/{job_id}/report` — retrieve a deterministic human-readable report projection.
- `POST /v1/research-claims` — create a tenant-scoped Research Claim.
- `GET /v1/research-claims/{claim_id}` — retrieve a workspace-scoped Research Claim.
- `GET /v1/research-claims` — list Research Claims with bounded tenant-scoped pagination.

The initial MVP accepts only the frozen XAUUSD M1 workflow.

## 5. Research Claim API semantics

Research Claim creation is bound to the authenticated `TenantContext`; request bodies never supply or override `workspace_id` or `creator`. The API accepts only claim-intent fields and does not permit clients to set evidence state, evidence hashes, plan lock state, or plan hash.

Creation uses a stable content-derived identifier scoped by workspace and authenticated creator, so repeating the identical create request returns the same durable claim identity. Claims are persisted through the explicit tenant-scoped persistence adapter; an unconfigured persistence boundary fails closed with HTTP 503.

Claim reads and pagination always pass the authenticated workspace to the persistence adapter. Cross-workspace lookups return HTTP 404.

## 6. Research run lifecycle

Allowed persisted states:

`queued -> running -> succeeded`

Failure/cancellation are terminal:

`running -> failed`

`queued/running -> cancelled`

Workers use fenced leases. An expired lease may be reclaimed; a stale lease token cannot finalize a run.

## 7. Idempotency

`POST /v1/research-runs` requires `Idempotency-Key`.

The key is scoped to the authenticated workspace. The request fingerprint covers all semantic request fields.

Reusing a key with a different fingerprint returns HTTP 409.

Production semantics must reserve the key atomically with the mutation so concurrent identical requests cannot create duplicate durable jobs.

## 8. Correlation

Every response receives `X-Request-ID`. A supplied value is bounded to 128 characters; otherwise the server generates one.

## 9. Error contract

Errors use the framework HTTP error envelope and stable human-readable `detail` values.

Important statuses:

- 400 — malformed/unsupported request.
- 401 — invalid authentication/signature.
- 404 — resource not visible in the authenticated workspace.
- 409 — conflicting idempotency or state.
- 413 — upload exceeds the effective plan limit.
- 429 — rate/concurrency limit exceeded.
- 402 — research usage entitlement exhausted.
- 503 — required infrastructure is unavailable.

Internal exception details and secrets are not returned to clients.

## 10. Authorization model

Every tenant-owned read/write is scoped by authenticated workspace.

Database defense in depth uses Supabase RLS for tenant-owned tables. Trusted server-side RPCs additionally require explicit workspace/resource matching.

Membership roles are resolved from server-side `workspace_member.role`; client claims and profile metadata are never used for authorization.

| Capability | Owner | Admin | Researcher | Viewer |
|---|---:|---:|---:|---:|
| Read own workspace identity | yes | yes | yes | yes |
| Read tenant datasets/versions | yes | yes | yes | yes |
| Upload dataset | yes | yes | yes | no |
| Append dataset version | yes | yes | yes | no |
| Create research run | yes | yes | yes | no |
| Read research runs | yes | yes | yes | yes |
| Membership administration | reserved for future API | reserved for future API | no | no |
| Billing/subscription mutation | server-side webhook only | server-side webhook only | server-side webhook only | server-side webhook only |

The current API exposes no user-facing membership-management or billing-management endpoints. Those permissions are therefore not implicitly granted by role; future endpoints must add explicit policy entries and tests before implementation.

Forbidden role actions return HTTP 403. Cross-workspace resource lookups remain 404 where the resource is not visible to the authenticated workspace.

## 11. Research integrity

API code must not:

- modify immutable dataset content identity;
- manufacture evidence;
- turn an inconclusive result into a positive result;
- bypass temporal validation;
- accept LLM-generated statistics as scientific evidence;
- introduce broker execution into the research product.

## 12. Compatibility gate

Before release, the exact release commit must pass:

1. Python test matrix.
2. Ruff lint.
3. Native C++/nanobind integration.
4. Health Evidence checks.
5. Tenant-isolation tests.
6. Idempotency/concurrency tests.
7. Migration compatibility checks.
8. Staging end-to-end research execution.

A green CI run is software evidence, not scientific evidence.
