# QROS Frontend Boundary V1

Status: implementation-ready boundary; framework and visual design intentionally undecided.

## Existing server boundary

The frontend can target the versioned API without inventing a new backend contract:

- GET /v1/me — authenticated identity/workspace context.
- POST /v1/datasets — create dataset and upload content.
- GET /v1/datasets/{dataset_id}/versions — list dataset versions.
- POST /v1/research-runs — submit a governed research run.
- GET /v1/research-runs/{job_id} — run lifecycle/status.
- GET /v1/research-runs/{job_id}/result — result identity and result payload.
- GET /v1/research-runs/{job_id}/report — research report.
- Claim, validation, finding, and evidence routes are registered by their dedicated SaaS route modules.
- POST /v1/billing/webhook is provider-to-provider infrastructure and is not a browser workflow.
- /readyz, /healthz, and /metrics are operational endpoints; only the first two have a normal deployment-readiness role.

## Required browser states

Every resource screen must represent loading, empty, success, authorization failure, validation failure, transient/server failure, and stale/retry state while a background run is active.

## Tenant boundary

The browser must treat workspace identity returned by the API as authoritative. It must never accept a workspace/tenant identifier from URL state as proof of authorization. Resource IDs may be displayed or routed, but authorization remains server-side.

## Research workflow

The minimum UI sequence is: Identity → Workspace → Dataset → Dataset Version → Claim → Plan → Research Run → Queue/Running → Result → Validation → Evidence/Finding.

The UI should render server lifecycle states rather than infer completion from client timers.

## Provenance display

For result/evidence views, expose server-provided identifiers and hashes needed to trace dataset/version identity, research run identity, result identity, evidence/finding identity, provenance/content hashes, and validation state.

Do not reconstruct or recalculate governance hashes in browser code.

## Errors and correlation

Preserve the API request_id / correlation_id returned by error payloads and expose them in support-oriented error details. Do not render sensitive fields from error payloads.

## Billing and usage

Browser billing surfaces should consume server entitlement/usage state. They must not calculate authorization or entitlement locally. Payment-provider secrets and webhook signatures never enter browser state.

## Architecture decision still external

This document deliberately does not choose React/Next/Vite, routing libraries, design system, hosting model, or authentication SDK. Those choices are product/engineering architecture decisions. The API boundary above is sufficient to start implementation once that decision is made.