# QROS SaaS Authorization Matrix

**Executable source of truth:** `researchos/saas/auth/authorization.py`  
**Route gate:** every `/v1/*` route must carry `@require_permission(resource, action)`.  
**Role source:** server-resolved `TenantContext.role`.

## Matrix

Legend: **✓** allowed, **—** forbidden.

### owner
| Resource | create | read | list | update | delete |
|---|---:|---:|---:|---:|---:|
| dataset | ✓ | ✓ | ✓ | ✓ | ✓ |
| job | ✓ | ✓ | ✓ | ✓ | ✓ |
| evidence | ✓ | ✓ | ✓ | ✓ | ✓ |
| finding | ✓ | ✓ | ✓ | ✓ | ✓ |
| billing | ✓ | ✓ | ✓ | ✓ | ✓ |
| workspace | ✓ | ✓ | ✓ | ✓ | ✓ |

### admin
| Resource | create | read | list | update | delete |
|---|---:|---:|---:|---:|---:|
| dataset | ✓ | ✓ | ✓ | ✓ | ✓ |
| job | ✓ | ✓ | ✓ | ✓ | ✓ |
| evidence | — | ✓ | ✓ | — | — |
| finding | ✓ | ✓ | ✓ | — | — |
| billing | — | ✓ | ✓ | ✓ | — |
| workspace | — | ✓ | ✓ | ✓ | — |

### researcher
| Resource | create | read | list | update | delete |
|---|---:|---:|---:|---:|---:|
| dataset | ✓ | ✓ | ✓ | — | — |
| job | ✓ | ✓ | ✓ | — | — |
| evidence | — | ✓ | ✓ | — | — |
| finding | ✓ | ✓ | ✓ | — | — |
| billing | — | — | — | — | — |
| workspace | — | ✓ | ✓ | — | — |

### viewer
| Resource | create | read | list | update | delete |
|---|---:|---:|---:|---:|---:|
| dataset | — | ✓ | ✓ | — | — |
| job | — | ✓ | ✓ | — | — |
| evidence | — | ✓ | ✓ | — | — |
| finding | — | ✓ | ✓ | — | — |
| billing | — | ✓ | ✓ | — | — |
| workspace | — | ✓ | ✓ | — | — |

### billing
| Resource | create | read | list | update | delete |
|---|---:|---:|---:|---:|---:|
| dataset | — | ✓ | ✓ | — | — |
| job | — | ✓ | ✓ | — | — |
| evidence | — | ✓ | ✓ | — | — |
| finding | — | ✓ | ✓ | — | — |
| billing | ✓ | ✓ | ✓ | ✓ | — |
| workspace | — | ✓ | ✓ | — | — |

## Route mapping

| Route | Capability |
|---|---|
| GET /v1/me | workspace/read |
| POST /v1/datasets | dataset/create |
| POST /v1/datasets/<dataset_id>/versions | dataset/update |
| GET /v1/datasets/<dataset_id>/versions | dataset/list |
| GET /v1/datasets/<dataset_id>/versions/<version_id>/download | dataset/read |
| POST /v1/research-runs | job/create |
| GET /v1/research-runs | job/list |
| GET /v1/research-runs/<job_id> | job/read |
| GET /v1/research-runs/<job_id>/result | job/read |
| GET /v1/research-runs/<job_id>/report | job/read |
| GET /v1/research-runs/<job_id>/evidence | evidence/list |
| POST /v1/research-runs/<job_id>/validation | job/update |
| GET /v1/research-runs/<job_id>/validation | job/read |
| POST /v1/research-runs/<job_id>/finding | finding/create |
| GET /v1/research-runs/<job_id>/finding | finding/read |
| POST /v1/research-claims | job/create |
| GET /v1/research-claims | job/list |
| GET /v1/research-claims/<claim_id> | job/read |
| POST /v1/research-claims/<claim_id>/plan-lock | job/update |
| POST /v1/billing/webhook | billing/create, service principal |

The billing webhook is a provider-signed server callback rather than a user JWT route. It is still explicitly decorated; `service_principal=True` means HMAC/provider authentication is the authorization mechanism.

## Enforcement

`require_permission()` requires a `TenantContext` for user routes and returns HTTP 403 for a denied capability. Missing authorization context is HTTP 500, making a missing dependency a fail-closed programming error.

CI statically scans every `/v1` FastAPI route and fails if the route has no `@require_permission`. Authorization tests exercise all 5 roles × 6 resources × 5 actions and verify representative HTTP behavior.

Resource aliases `research-run` and `research-claim` resolve to the `job` capability family.
