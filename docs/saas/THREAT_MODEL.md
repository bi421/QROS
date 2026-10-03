# QROS SaaS Threat Model

## Assets

| Asset | Security objective |
|---|---|
| Tenant data | Confidentiality, integrity, and strict tenant isolation |
| JWT | Authenticity and integrity of identity, tenant, role, and session claims |
| Storage | Tenant-scoped confidentiality and integrity of uploaded datasets |

## Threats and mitigations

| Threat | Mitigations |
|---|---|
| Cross-tenant read | Server-resolved TenantContext; PostgreSQL RLS; Storage policies bind tenant path to the JWT tenant claim; real tenant-isolation integration tests. |
| JWT tampering | Validate JWT signature and session state server-side; never trust client-supplied tenant/role fields; resolve membership from trusted persistence; fail closed. |
| Path traversal (`../../`) | Canonical storage path generation; reject non-canonical paths before storage access; allow only `tenant/{UUID}/datasets/{sha256}/{version}`. |
| Idempotency-key enumeration | Scope idempotency records by tenant; opaque UUID job identifiers; cross-tenant requests resolve as not found; tenant-isolation tests. |
| `service_role` leak | Keep service-role credentials server-side only; never serialize them into API responses, logs, queue payloads, or browser configuration. |
| Billing bypass | Resolve entitlements server-side; enforce quotas before creation/storage; verify webhook signatures and reject replayed events. |

## Production error policy

Internal exceptions are converted to generic `Internal error` responses containing only the request identifier and stable error metadata. Stack traces, SQL statements, credentials, JWTs, and secret keys are never returned to clients.

## Residual risks

- Compromised signing keys or Supabase service credentials remain high-impact infrastructure risks and require rotation and least privilege.
- RLS depends on migrations being applied without drift; production schema parity checks remain mandatory.
- Logs can contain sensitive identifiers if future code binds unreviewed fields; structured-log review and red-team tests are required.
- Availability attacks such as credential stuffing, upload flooding, and queue exhaustion require operational rate limits and monitoring.
- JWT/session compromise outside the application boundary cannot be eliminated by application authorization alone; revocation and short-lived sessions reduce exposure.