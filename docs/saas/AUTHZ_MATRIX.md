# QROS SaaS Authorization Matrix

Default-deny authorization. Tenant identity comes from authenticated TenantContext; request payloads cannot select a workspace.

| Resource | owner | admin | researcher | viewer |
|---|---|---|---|---|
| workspace | CRUD | CRUD* | read/list | read/list |
| dataset | CRUD | CRUD | CRU | RL |
| dataset_version | CRUD | CRUD | CRU | RL |
| job | CRUD | CRUD | CRU | RL |
| claim | CRUD | CRUD | CRU | RL |
| plan | CRUD | CRUD | CRU | RL |
| evidence | CRUD | CRUD | CRU | RL |
| finding | CRUD | CRUD | CRU | RL |
| billing | CRUD | RLU | denied | denied |

CRU means create/read/update; RL means read/list. Delete is intentionally absent for researcher/viewer.

Authorization is implemented in researchos/saas/auth/permissions.py. New protected routes must use the same resource/action vocabulary and default-deny behavior.
