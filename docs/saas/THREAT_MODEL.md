# SaaS Threat Model

**Scope:** QROS multi-tenant SaaS HTTP, Supabase persistence, private storage, and asynchronous worker boundaries.

## Assets

| Asset | Security property |
|---|---|
| Tenant data | Confidentiality and integrity across workspaces; no cross-tenant reads or writes. |
| JWT / authenticated identity | Authenticity and integrity of the caller identity and authorized session. |
| Storage objects | Tenant isolation, path integrity, confidentiality, and immutable content identity. |

## Threats and mitigations

### 1. Cross-tenant read

**Threat:** A caller changes a workspace/resource identifier or guesses another tenant's dataset/job UUID and attempts to read it.

**Mitigations:**
- Resolve authorization from the authenticated TenantContext; never trust a client-supplied workspace identifier.
- Scope application reads and writes by workspace_id.
- Enforce Supabase RLS as database defense in depth.
- Worker operations carry an explicit workspace ID and use tenant-scoped, lease-fenced operations.
- Return 404 Not Found for resources that are not visible to the authenticated workspace so existence is not disclosed.

### 2. JWT tampering

**Threat:** An attacker modifies claims such as tenant_id/workspace identity or otherwise presents a forged bearer token.

**Mitigations:**
- Verify the bearer token through Supabase Auth before constructing TenantContext.
- Derive the authorized workspace from the server-side membership resolver keyed by authenticated sub.
- Do not authorize from user-editable JWT/profile metadata such as a tenant/workspace claim.
- Invalid/forged tokens fail with 401; unauthorized membership fails with 403.

### 3. Path traversal (`../../`)

**Threat:** A dataset name or object path is manipulated with ../, absolute separators, or backslashes to escape the intended storage namespace.

**Mitigations:**
- Reject path-like dataset names at the HTTP boundary with 400 INVALID_PATH.
- Storage object keys are generated from validated UUIDs plus a SHA-256 digest; client-provided names are not used as storage paths.
- Private storage is tenant-scoped and accessed server-side.

### 4. Idempotency-key enumeration

**Threat:** An attacker probes idempotency keys to infer another tenant's request history or resource existence.

**Mitigations:**
- Idempotency keys are scoped to the authenticated workspace.
- Production persistence reserves keys atomically with the tenant/workspace identity.
- Cross-workspace resource lookup remains 404, rather than revealing whether a resource exists.
- Keys are bounded in length and are not treated as authorization credentials.

### 5. service_role leak

**Threat:** The Supabase service_role credential is exposed to browser clients, logs, error responses, or untrusted request input.

**Mitigations:**
- The credential is server-only and loaded from deployment secrets.
- Browser/API responses never include service-role credentials.
- Workers operate through the ResearchJobStore abstraction and tenant-scoped server-side RPC contracts rather than accepting a role from the caller.
- Error responses are sanitized and contain only a generic message plus request ID for unexpected failures.
- Tests assert the worker boundary does not emit or depend on a service-role credential.

### 6. Billing bypass

**Threat:** A caller changes plan/entitlement data or skips usage enforcement to obtain paid capacity without a valid subscription.

**Mitigations:**
- Effective plan is resolved server-side from the workspace subscription.
- Client-controlled profile/JWT metadata is not used as the billing authority.
- Research run limits and concurrency limits are checked against the server-side workspace.
- Billing webhook events require an HMAC signature and are idempotently processed.
- Invalid subscription state fails closed rather than silently granting elevated access.

## Production error-response policy

Unexpected server exceptions must not expose implementation details. Production responses use:
- HTTP 500
- detail: "Internal error"
- error.code: "internal_error"
- error.message: "Internal error"
- error.request_id: <correlation ID>
- X-Request-ID: <same correlation ID>

Stack traces, SQL statements, filesystem paths, environment variables, JWT contents, and service-role credentials are server-side logging concerns only and must never be returned to clients.

Expected authentication, authorization, validation, rate-limit, billing, and not-found errors may retain their stable public contract.

## Residual risks

- A compromised server or Supabase service-role credential can bypass database RLS; secret rotation and deployment isolation remain operational controls.
- A valid authenticated user's own credentials can still access everything legitimately authorized for that workspace.
- Object-storage misconfiguration outside the application/RLS boundary can still expose private objects.
- UUID identifiers reduce practical enumeration risk but are not an authorization mechanism.
- Logging infrastructure can become a secondary secret-disclosure surface and requires access control, retention limits, and secret redaction.
- JWT verification depends on the correctness and availability of the configured Supabase Auth boundary.
- Billing-provider compromise or a forged webhook secret could affect entitlement state; HMAC protection and server-side validation reduce but do not eliminate that risk.