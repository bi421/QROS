# QROS API Contract V1 — Golden Path

Every customer endpoint follows:
HTTP -> Auth -> TenantContext -> Authorization -> Domain -> Persistence

## Workflow surface
- GET /healthz
- GET /readyz
- GET /v1/me
- POST /v1/datasets
- POST /v1/datasets/{dataset_id}/versions
- GET /v1/datasets/{dataset_id}/versions
- GET /v1/datasets/{dataset_id}/versions/{version_id}/download
- POST /v1/research-runs
- GET /v1/research-runs
- GET /v1/research-runs/{job_id}
- GET /v1/research-runs/{job_id}/result
- GET /v1/research-runs/{job_id}/report
- GET /v1/research-runs/{job_id}/evidence
- POST /v1/research-claims
- GET /v1/research-claims
- GET /v1/research-claims/{claim_id}

Writes require owner/admin/researcher unless a narrower domain policy applies. Viewer is read-only. Cross-tenant lookup returns 404.
