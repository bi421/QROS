# QROS SaaS Authorization Matrix

**Executable source of truth:** `researchos/saas/auth/permissions.py`  
**Route gate:** every `/v1/*` route must carry exactly one `@require_permission(resource, action)`.  
**Role source:** server-resolved `TenantContext.role`.

Legend: **✓** allowed, **—** denied. Columns are **create / read / list / update / delete**.

| Resource | owner | admin | researcher | viewer | billing_admin |
|---|---|---|---|---|---|
| workspace | ✓/✓/✓/✓/✓ | —/✓/✓/✓/— | —/✓/✓/—/— | —/✓/✓/—/— | —/✓/✓/—/— |
| dataset | ✓/✓/✓/✓/✓ | ✓/✓/✓/✓/✓ | ✓/✓/✓/✓/— | —/✓/✓/—/— | —/✓/✓/—/— |
| dataset_version | ✓/✓/✓/✓/✓ | ✓/✓/✓/✓/✓ | ✓/✓/✓/✓/— | —/✓/✓/—/— | —/✓/✓/—/— |
| job | ✓/✓/✓/✓/✓ | ✓/✓/✓/✓/✓ | ✓/✓/✓/✓/— | —/✓/✓/—/— | —/✓/✓/—/— |
| claim | ✓/✓/✓/✓/✓ | ✓/✓/✓/✓/— | ✓/✓/✓/✓/— | —/✓/✓/—/— | —/✓/✓/—/— |
| plan | ✓/✓/✓/✓/✓ | ✓/✓/✓/✓/— | ✓/✓/✓/✓/— | —/✓/✓/—/— | —/✓/✓/—/— |
| evidence | ✓/✓/✓/✓/✓ | —/✓/✓/—/— | —/✓/✓/—/— | —/✓/✓/—/— | —/✓/✓/—/— |
| finding | ✓/✓/✓/✓/✓ | ✓/✓/✓/✓/— | ✓/✓/✓/✓/— | —/✓/✓/—/— | —/✓/✓/—/— |
| billing | ✓/✓/✓/✓/✓ | —/✓/✓/✓/— | —/—/—/—/— | —/—/—/—/— | ✓/✓/✓/✓/— |

## Current v1 route bindings

| Route family | Capability |
|---|---|
| `/v1/me` | workspace/read |
| `/v1/workspaces/{workspace_id}` | workspace/delete/read |
| `/v1/datasets` | dataset/create/list |
| `/v1/datasets/{dataset_id}/versions` | dataset/update/list/read |
| `/v1/research-runs` | job/create/list/read |
| `/v1/research-runs/{job_id}/validation` | job/update/read |
| `/v1/research-runs/{job_id}/evidence` | evidence/list |
| `/v1/research-runs/{job_id}/finding` | finding/create/read |
| `/v1/findings` | finding/list |
| `/v1/research-claims` | claim/create/list/read |
| `/v1/research-claims/{claim_id}/plan-lock` | plan/update |
| `/v1/billing/webhook` | billing/create, service principal |

The billing webhook is provider-authenticated and explicitly decorated with `service_principal=True`; it is not a user-role route.

## Enforcement

`require_permission()` reads the server-resolved `TenantContext.role`. Request payloads and workspace headers cannot override it. A denied request returns HTTP 403 with `code=FORBIDDEN` and the request ID.

CI runs:

```text
python scripts/check_authz_coverage.py
```

and fails unless every `/v1/*` route has exactly one authorization decorator.

The viewer role is denied `job:create`, therefore **POST /v1/research-runs** returns 403 before the handler performs job creation.
