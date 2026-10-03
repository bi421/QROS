# QROS Security and Architecture Governance — 2026

**Status:** Mandatory engineering control  
**Scope:** QROS research core, SaaS APIs, persistence, workers, storage, audit, retention, and any future execution integration.

This document is the security/architecture control plane for QROS. It converts architectural principles into explicit invariants that must survive implementation changes.

## 1. Trust boundaries

QROS has five explicit trust domains:

1. **Research domain** — deterministic research computation and immutable research artifacts.
2. **SaaS control plane** — authentication, tenant context, authorization, API policy, jobs, billing/usage, and audit.
3. **Persistence/data plane** — Supabase/Postgres, object storage, queues, and durable artifacts.
4. **Operator domain** — migrations, recovery, retention approval, incident response, and production administration.
5. **Execution domain** — future live execution only; it is never an implicit dependency of research or SaaS code.

Crossing a boundary requires an explicit contract. No module may infer authority from a resource identifier.

## 2. Security invariants

The following are non-negotiable:

- **Tenant authority is server-derived.** Client-supplied workspace/resource ownership fields are never authoritative.
- **Authorization is fail-closed.** Missing, malformed, ambiguous, or stale authorization context denies sensitive operations.
- **RLS is defense in depth.** Application authorization does not replace database row-level isolation.
- **Sensitive writes require explicit authorization.** Authentication alone is not authorization.
- **Destructive operations require independent gates:** eligibility, approval, tenant authorization, dependency resolution, audit availability, and an idempotent destructive adapter.
- **Audit metadata is non-secret.** Tokens, credentials, raw payloads, and sensitive user data must not be placed in audit metadata.
- **Research/execution is one-way.** Research code cannot create broker/exchange side effects.
- **Historical artifacts are immutable.** Security fixes must not mutate research history to hide evidence.
- **Unknown state is unsafe state.** Unknown dependency, authorization, retention, or provenance state must not be interpreted as safe.
- **Secrets never cross the client boundary.** Service credentials and privileged database keys remain server-side.
- **Authorization data must come from server-controlled sources.** User-editable profile metadata must never become an authorization primitive.
- **Privileged database code is exceptional.** SECURITY DEFINER requires an explicit reviewed contract, restricted schema exposure, and authorization checks.
- **Every sensitive operation is traceable.** Request correlation and tenant context must be available where an audit event is required.

## 3. Architecture rules

### 3.1 Tenant context
Every tenant-owned operation must receive an already-authorized tenant context. Resource IDs are opaque identifiers, not tenant selectors.

### 3.2 Persistence
Persistence adapters must preserve tenant scope at the storage boundary. A repository method that can access multiple tenants without an explicit tenant context is prohibited.

### 3.3 API
API handlers must validate input size, shape, authorization, and tenant context before invoking persistence or research services.

### 3.4 Jobs
Durable jobs must preserve tenant identity, provenance, idempotency, and explicit state transitions. Workers must not reconstruct tenant authority from arbitrary payload fields.

### 3.5 Audit
Audit events are append-oriented security records. Audit failure on a pre-destructive boundary blocks destruction. Post-destructive audit failure must enter an explicit reconciliation path.

### 3.6 Retention
Retention eligibility is separate from deletion. Production destructive deletion remains disabled until dependency resolution, idempotency, reconciliation, and backup/restore have been verified in the target environment.

### 3.7 Research integrity
Security or operational code must not weaken evidence provenance, determinism, validation, uncertainty reporting, or replication requirements.

## 4. Change-risk classification

Every architecture/security change is classified before merge:

- **R0:** documentation/comments only.
- **R1:** isolated pure logic with no trust-boundary effect.
- **R2:** API, persistence, job, storage, authorization, or audit behavior change.
- **R3:** tenant isolation, RLS, secrets, destructive deletion, migrations, privileged SQL, or research/execution boundary change.

R2 requires unit + integration + failure-path coverage and exact-release CI evidence.

R3 additionally requires explicit security review evidence, tenant-isolation coverage, rollback/recovery analysis, and target-environment verification where applicable.

## 5. Forbidden shortcuts

- Trusting client workspace/owner identifiers.
- Treating authenticated as sufficient authorization.
- Bypassing RLS to make an application work.
- Logging secrets or raw authentication material.
- Catching security exceptions and continuing.
- Making destructive operations best-effort.
- Using a resource ID to infer tenant ownership.
- Disabling a failing security test without changing and documenting the contract.
- Claiming production readiness from unit tests alone.

## 6. Release gate

A security-sensitive release must have:

CONTRACT → IMPLEMENTATION → UNIT → FAILURE → INTEGRATION → TENANT ISOLATION → DETERMINISM → SECURITY REVIEW → EXACT CI → RELEASE EVIDENCE

If any required evidence is missing, the capability remains unreleased.

## 7. Incident and recovery rule

Security incidents, authorization failures, audit gaps, and destructive-operation inconsistencies are evidence-producing events. The system must preserve enough immutable metadata to reconstruct:

- tenant/workspace;
- actor where known;
- request/correlation identifier;
- resource;
- action;
- decision;
- relevant non-secret metadata;
- timestamp;
- resulting state.

No incident response procedure may erase the underlying research or audit history.

## 8. Architecture decision rule

When a proposed feature conflicts with a trust boundary, isolate the feature behind an explicit adapter or separate service. Do not weaken the boundary to reduce implementation effort.

This policy is subordinate only to a formally documented architecture decision that preserves or strengthens the invariants above.
