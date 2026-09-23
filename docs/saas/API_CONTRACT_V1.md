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
- `role` — server-authoritative workspace membership role (`owner`, `admin`, `researcher`, `viewer`, `billing`).

## 4. Endpoints

### System

- `GET /healthz` — process health.
- `POST /v1/billing/webhook` — provider-signed billing event callback.
- `GET /readyz` — dependency/readiness boundary.

### Identity

- `GET /v1/me` — returns the authenticated user, workspace, and effective plan.

### Datasets

- `POST /v1/datasets` — create a dataset and immutable version from an upload.
- `POST /v1/datasets/{dataset_id}/versions` — append an immutable dataset version.
- `GET /v1/datasets` — list datasets visible to the authenticated workspace; optional `name`, `limit`, and `offset` filters.
- `GET /v1/datasets/{dataset_id}/versions` — list versions visible to the authenticated workspace with the standard pagination envelope.
- `GET /v1/datasets/{dataset_id}/versions/{version_id}/download` — issue a short-lived private download URL after tenant authorization.
- `DELETE /v1/datasets/{dataset_id}/versions/{version_id}` — delete an authorized dataset version.

## 4.1 List response contract

Every list endpoint uses the same query parameters and response envelope:

- Query: `page` (default `1`), `page_size` (default `20`, maximum `100`), `sort_by` (endpoint allowlist), `sort_order` (`asc` or `desc`), and supported `filter[...]` parameters such as `filter[status]` and `filter[tenant_id]`.
- Unknown or malformed filters return HTTP 400 with code `INVALID_FILTER`.
- Unsupported `sort_by` returns HTTP 400 with code `INVALID_SORT`.
- The response body is:

```json
{
  "data": [],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100,
    "total_pages": 5
  },
  "request_id": "01JQROSREQUEST123"
}
```

`filter[tenant_id]` is never used to widen authorization scope; it can only constrain results to the authenticated tenant. A different tenant value produces an empty result set.

Dataset bytes are streamed through a bounded SHA-256 calculation before persistence. Storage paths are tenant-scoped and content-addressed.

### Research

- `POST /v1/research-runs` — enqueue a frozen research workflow.
- `GET /v1/research-runs` — list workspace-scoped jobs with bounded status/workflow filters and pagination.
- `GET /v1/research-runs/{job_id}` — retrieve a workspace-scoped job.
- `GET /v1/research-runs/{job_id}/logs` — retrieve the tenant-scoped deterministic lifecycle log projection with the standard pagination envelope.
- `GET /v1/jobs/{job_id}/logs` — compatibility alias for the research-run lifecycle log projection.
- `GET /v1/research-runs/{job_id}/result` — retrieve the immutable governed result projection.
- `GET /v1/research-runs/{job_id}/evidence` — retrieve tenant-scoped stored evidence lineage with the standard pagination envelope.
- `POST /v1/research-runs/{job_id}/validation` — persist a governed validation projection for an available research result.
- `GET /v1/research-runs/{job_id}/validation` — retrieve the governed validation projection.
- `POST /v1/research-runs/{job_id}/finding` — persist a finding only from a validated research result.
- `GET /v1/research-runs/{job_id}/finding` — retrieve the governed finding projection.
- `GET /v1/research-runs/{job_id}/report` — retrieve a deterministic human-readable report projection.
- `POST /v1/research-claims` — create a tenant-scoped Research Claim.
- `GET /v1/research-claims/{claim_id}` — retrieve a workspace-scoped Research Claim.
- `POST /v1/research-claims/{claim_id}/plan-lock` — lock the immutable research plan for a claim.
- `GET /v1/research-claims/{claim_id}/evidence-graph` — retrieve tenant-scoped evidence lineage associated with the claim with the standard pagination envelope.
- `GET /v1/claims/{claim_id}/evidence_graph` — compatibility alias for the claim evidence graph.
- `GET /v1/research-claims` — list Research Claims with bounded tenant-scoped pagination.

### Findings

- `GET /v1/findings` — list tenant-scoped governed findings with bounded pagination, status filtering, and deterministic sorting.

### Workspace compliance

- `DELETE /v1/workspaces/{workspace_id}` — soft-delete the authenticated workspace and return a deletion receipt with the scheduled purge date.
- `GET /v1/workspaces/{workspace_id}/export` — download a machine-readable ZIP export containing tenant datasets, research jobs, evidence envelopes, and related lifecycle records.

Workspace deletion is fail-closed: tenant rows receive `deleted_at`, list/read persistence queries exclude soft-deleted rows, and physical purge is allowed only after the workspace retention window (30 days by default; production-configurable). Evidence hashes are retained in immutable deletion tombstones so historical lineage cannot be resurrected.

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

Every error response is exactly the structured JSON envelope:

```json
{
  "code": "not_found",
  "message": "research run not found",
  "request_id": "01JQROSREQUEST123",
  "correlation_id": "01JQROSREQUEST123"
}
```

`request_id` and `correlation_id` are identical for one HTTP request. Every response, including errors, also carries the `X-Request-ID` response header with that value.

Stable error codes:
- `bad_request`
- `unauthorized`
- `payment_required`
- `forbidden`
- `not_found`
- `conflict`
- `payload_too_large`
- `validation_error`
- `rate_limited`
- `internal_error`
- `service_unavailable`

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

Every tenant-owned read/write is scoped by authenticated workspace and the executable role matrix in `researchos/saas/auth/authorization.py`.

See **`docs/saas/AUTHZ_MATRIX.md`** for the complete 5-role × 6-resource × 5-action contract. Every `/v1` route is statically required to carry `@require_permission(resource, action)`; missing coverage fails CI.

Membership roles are resolved from server-side `workspace_member.role`; client claims and profile metadata are never used for authorization. Forbidden role actions return HTTP 403. Cross-workspace resource lookups remain 404 where the resource is not visible to the authenticated workspace.

The billing webhook is a provider-signed server callback and is explicitly decorated with the billing capability using a service principal; it does not accept user JWT authorization.

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
