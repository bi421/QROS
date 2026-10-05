# QROS SaaS Roadmap

> **Current state:** 🟡 **IN PROGRESS — NOT PRODUCTION-READY**
>
> QROS has a substantial governed SaaS foundation. The remaining work is concentrated in **staging validation, operational recovery, observability, product UI, and commercial validation**.
>
> **Rule:** Green code/CI does not equal production readiness. Operational claims require environment-specific evidence.

---

## Executive Status

| Area | Status | Current position |
|---|---|---|
| Research governance | 🟢 Complete | Core claim/plan/evidence/result governance implemented |
| Tenant security | 🟢 Complete | RLS, authorization, isolation tests and session boundary implemented |
| API foundation | 🟢 Complete | Versioned API, validation, rate limits, idempotency and errors |
| Database migrations | 🟡 Blocked (staging parity) | 46 staging migration rows after the forward-only `20261005050000_dataset_version_feed_reconciliation` reconciliation; current main now contains 64 canonical migration files. The staging migration history ends with worker execution version `20260928103556` under the historical remote display name `20260928103225_saas_worker_queue_consumer`. A normalized comparison shows 17 canonical migration names are not represented in the staging history: 9 pre-worker hardening migrations and 8 migrations after the worker reconciliation point. Because historical staging migration names were rewritten, this is a migration-history/schema-parity blocker and does not by itself prove that every SQL change is absent from the live schema. The exact missing set must be reconciled and schema-verified before M1 can pass. |
| Staging Golden Path | 🟡 Blocked | Auth/application identities and end-to-end operational evidence pending |
| Disaster Recovery | 🔴 Blocked | Isolated recovery target and recovery storage not provisioned |
| Observability | 🟡 In progress | Production-grade acceptance evidence pending |
| Product UI | 🔴 Not complete | Core SaaS UI remains to be built |
| Billing/commercial | 🔴 Not complete | Paid pilot and external-user evidence pending |

---

## Current Milestone

### M1 — Staging Validation & Operational Readiness

**Goal:** prove that the implemented SaaS contracts work together in a real, isolated staging environment before any production-readiness claim.

### Exit criteria

- [x] Exact canonical-vs-live migration-name audit completed: 64 canonical files, 46 live rows, 20 literal-name gaps. Semantic reconciliation found no additional missing schema behavior; historical migration names remain untouched.
- [x] Staging schema/security objects verified for the reconciled SaaS contracts; semantic migration reconciliation is complete for all 20 literal-name gaps.
- [ ] Two controlled staging identities verified.
- [ ] Real API tenant isolation verified.
- [ ] Complete governed Golden Path executed.
- [ ] Idempotency/retry/worker behavior verified.
- [ ] Observability acceptance evidence captured.
- [ ] DR infrastructure gate passed.

**Current gate:** 🟡 **BLOCKED / NOT VERIFIED**

---

# Delivery Roadmap

## 1. Research Governance — 🟢 COMPLETE

- [x] Research Claim domain and persistence contract.
- [x] Immutable/content-addressed Research Plan.
- [x] One-time plan locking.
- [x] Claim → Plan → Evidence lineage.
- [x] Experiment / Run / Result / Validation / Finding traversal.
- [x] Contradiction and replication edges.
- [x] Governed AnalysisResult.
- [x] Probability/edge eligibility registry.
- [x] Calibration and uncertainty contracts.
- [x] OOS / replication state.
- [x] Multiple-testing controls.
- [x] Economic cost/slippage context.
- [x] Deterministic research manifests.
- [x] Governed research report export.

---

## 2. Multi-Tenant Security — 🟢 IMPLEMENTED

### Tenant boundary
- [x] Mandatory workspace/tenant context.
- [x] Fail-closed ambiguous workspace resolution.
- [x] Explicit workspace selection.
- [x] Tenant-scoped persistence.
- [x] Tenant-scoped customer APIs.
- [x] RLS on QROS tenant-owned tables.

### Isolation
- [x] Cross-workspace read/write/delete tests.
- [x] Workspace rebinding tests.
- [x] Parent/child workspace mismatch tests.
- [x] Privileged RPC boundary tests.
- [x] Result/Evidence Golden Path isolation tests.
- [x] Research Claim isolation tests.
- [x] Tenant-isolation red-team suite.

### Authentication
- [x] JWT role/audience/issuer/subject validation.
- [x] Authoritative session validation.
- [x] Revoked-session rejection.
- [x] Fail-closed session-store behavior.
- [x] Server-only session validator.
- [x] Restricted session-validation RPC.

---

## 3. Database & Migration Integrity — 🟡 IN PROGRESS

### Repository contract
- [x] Canonical migrations under `supabase/migrations/`.
- [x] Migration filename/order validation.
- [x] Migration security invariants.
- [x] Canonical migration-file count is tracked by repository tooling; do not hard-code a stale count in roadmap evidence.

### QROS Staging
- [x] Staging project exists.
- [x] Project ref: `yebwhcntiockckhdvawt`.
- [x] Region: `ap-northeast-1`.
- [x] PostgreSQL 17.6 / engine 17.
- [x] 45 migration rows observed; the worker migration is present under its historical remote display name.
- [ ] Current repository migration set must be fully reconciled with staging migration history and schema; current exact audit finds 20 historical canonical migration names not represented by live staging history; the missing `dataset_version_feed` schema contract was separately reconciled forward without rewriting history.
- [x] 23 public tables observed.
- [x] 23/23 public tables have RLS enabled; 0 disabled.

### Remaining
- [x] Verify the worker execution version `20260928103556` is present; its historical remote display name remains `20260928103225_saas_worker_queue_consumer` and is not rewritten.
- [x] Reconcile and verify the 20 canonical migrations not represented by live staging history; no additional forward-only schema migration was required.
- [x] Verify staging QROS tables, RLS state, public policies/triggers, and governed queue function grants.
- [x] Verify RLS is enabled on all 23 QROS public tables (23/23; 0 disabled).
- [x] Review staging Security Advisor findings.
- [x] Document the existing `pgtap`-in-public-schema warning; no live schema mutation performed.

> **Important:** Manual migration application proves the SQL was applied; it does **not** by itself prove canonical migration-history parity. Do not rewrite migration history merely to obtain a green check.

---

## 4. Dataset & Artifact Storage — 🟢 IMPLEMENTED / 🟡 OPERATIONAL VALIDATION

- [x] Tenant-scoped object storage abstraction.
- [x] Content-addressed artifacts.
- [x] Upload/download authorization.
- [x] Dataset version registry.
- [x] Reproducibility manifests.
- [x] Dataset-version path validation.
- [x] Retention eligibility contract.
- [x] Destructive retention executor.
- [ ] Production retention enablement.
- [ ] Storage recovery drill against isolated recovery infrastructure.

---

## 5. Durable Execution — 🟢 IMPLEMENTED / 🟡 OPERATIONAL VALIDATION

- [x] Idempotency keys.
- [x] Atomic durable reservation.
- [x] Durable job records.
- [x] State transitions.
- [x] Bounded retries.
- [x] Terminal states.
- [x] Worker heartbeat/lease.
- [x] Provenance-linked outputs.
- [ ] Staging worker-loss/restart drill.
- [ ] Queue/job recovery drill.
- [ ] Recovery evidence verification.

---

## 6. API Productization — 🟢 IMPLEMENTED / 🟡 STAGING VALIDATION

- [x] Stable versioned API.
- [x] Request validation and size limits.
- [x] Authorization matrix.
- [x] Rate limiting / abuse controls.
- [x] Pagination/filter/sort contracts.
- [x] Structured error model.
- [x] Idempotent research-run mutation.
- [x] Request correlation metadata.

### Remaining
- [ ] Verify real staging API with controlled Auth identities.
- [ ] Verify two-user/two-workspace isolation through the application path.
- [ ] Verify authorization failures through the real API.
- [ ] Execute complete staging Golden Path.

---

## 7. Product UI — 🔴 NOT COMPLETE

- [ ] Tenant/workspace shell.
- [ ] Claim creation and plan-lock workflow.
- [ ] Dataset workflow.
- [ ] Experiment/run/result explorer.
- [ ] Evidence lineage graph.
- [ ] Validation/finding/replication views.
- [x] Governed report export API.
- [ ] Audit trail UI.

---

## 8. Observability & Security — 🟡 IN PROGRESS

- [ ] Structured application logging.
- [ ] API metrics.
- [ ] API tracing.
- [ ] Durable-job metrics/tracing.
- [ ] Security-sensitive audit events.
- [ ] Secret/config validation.
- [ ] Dependency scanning.
- [ ] Container/image scanning.
- [ ] Threat-model review.
- [ ] Production observability acceptance test.
- [ ] Verify credential-bearing data never enters logs/evidence.

---

# Disaster Recovery

## 9. DR Repository Contract — 🟢 COMPLETE

- [x] Explicit backup-source authorization.
- [x] Production source rejected for governed DR drill.
- [x] Isolated/disposable restore target requirement.
- [x] Evidence manifest with explicit non-executed states.
- [x] Version-controlled DR infrastructure contract.
- [x] Version-controlled DR secret contract.
- [x] Release SHA binding.
- [x] Git-controlled vs externally provisioned infrastructure separation.

## 10. DR Infrastructure — 🔴 BLOCKED

### Source
- [x] Authoritative staging source exists.
- [ ] Record staging database identity.
- [ ] Record deployed staging release SHA.
- [ ] Independently verify staging is non-production.

### Recovery target
- [ ] Dedicated isolated PostgreSQL/Supabase target.
- [ ] Independent target identity.
- [ ] Target ≠ staging.
- [ ] Target ≠ production.
- [ ] Compatible PostgreSQL major.
- [ ] Recovery verification capability.

### Recovery storage
- [ ] Dedicated recovery S3 bucket/namespace.
- [ ] Region recorded.
- [ ] Scoped recovery credentials.
- [ ] Production bucket excluded.

### Staging application/auth
- [ ] `QROS_STAGING_BASE_URL`.
- [ ] Staging test identity.
- [ ] Independent isolation-test identity.
- [ ] Authorized operator.
- [ ] Evidence retention location.

### Required secret presence

The following GitHub Environment secrets must exist **without exposing their values**:

- [ ] `QROS_STAGING_DATABASE_URL`
- [ ] `QROS_BACKUP_SOURCE_ENVIRONMENT`
- [ ] `QROS_SOURCE_RELEASE_SHA`
- [ ] `QROS_STAGING_SUPABASE_URL`
- [ ] `QROS_STAGING_SUPABASE_SERVICE_ROLE_KEY`
- [ ] `QROS_STAGING_SUPABASE_ANON_KEY`
- [ ] `QROS_STAGING_BASE_URL`
- [ ] `QROS_STAGING_JWT`
- [ ] `QROS_STAGING_ISOLATION_JWT`
- [ ] `QROS_RECOVERY_S3_BUCKET`
- [ ] `QROS_RECOVERY_AWS_REGION`
- [ ] `QROS_RECOVERY_AWS_ACCESS_KEY_ID`
- [ ] `QROS_RECOVERY_AWS_SECRET_ACCESS_KEY`

### Gate rule

**DR Infrastructure = PASS only when every required source, target, storage, authentication, authorization, secret-presence and evidence-retention criterion is independently verified.**

Missing / unknown / unverified = **BLOCKED**.

---

## 11. DR Execution — ⏸ NOT STARTED

Do **not** dispatch recovery workflows while the infrastructure gate is blocked.

- [ ] Controlled staging backup.
- [ ] Backup integrity verification.
- [ ] Isolated restore.
- [ ] Canonical migration verification.
- [ ] PostgreSQL compatibility verification.
- [ ] Schema/security verification.
- [ ] RLS verification.
- [ ] Tenant-isolation verification.
- [ ] Critical-record verification.
- [ ] Dataset identity/hash verification.
- [ ] Object-storage recovery.
- [ ] Worker/queue recovery.
- [ ] Application health/readiness.
- [ ] Immutable DR evidence manifest.
- [ ] Actual RPO.
- [ ] Actual RTO.
- [ ] Operational runbook.

---

# Staging Golden Path

## 12. End-to-End Validation — 🟡 BLOCKED

Target workflow:

`Claim → Plan Lock → Dataset → Experiment/Run → Result → Evidence → Validation/Finding`

Required evidence:

- [ ] Staging project identity.
- [ ] Exact deployed release SHA.
- [ ] Canonical migration parity.
- [ ] Auth identities.
- [ ] Application endpoint.
- [ ] Controlled test data.
- [ ] Tenant isolation.
- [ ] Authorization failures.
- [ ] Idempotency/retry/lease behavior.
- [ ] Provenance/content hashes.
- [ ] Structured errors/correlation metadata.
- [ ] Exact-SHA CI evidence.
- [ ] Reproducible staging evidence bundle.

---

# Commercial Validation

## 13. Customer Evidence — 🔴 NOT STARTED

Engineering completeness is **not** commercial validation.

- [ ] Select one narrow customer research problem.
- [ ] Define measurable outcome.
- [ ] Define minimum input/data contract.
- [ ] Execute one complete governed workflow.
- [ ] Validate with an external user.
- [ ] Record feedback and failure modes.
- [ ] Define a paid pilot around a concrete research deliverable.
- [ ] Capture payment, repeat usage, or qualified pilot commitment as commercial evidence.

---

# Production Readiness Gate

QROS is **not production-ready** until all applicable gates below have independently observed evidence:

| Gate | Requirement |
|---|---|
| Research | Governance invariants verified |
| Security | Auth, authorization, RLS and tenant isolation verified |
| Database | Canonical migration/schema parity verified |
| API | Real staging Golden Path verified |
| Execution | Idempotency, retry, lease and provenance verified |
| DR | Backup/restore and recovery verified |
| Storage | Object recovery verified |
| Observability | Production telemetry verified |
| CI | Exact release SHA verified |
| Security review | No unresolved high-severity defect |
| Release | Reproducible/versioned artifact |
| Product | Staging and production Golden Paths verified |
| Commercial | External customer evidence recorded separately |

> **CI green ≠ production ready.**  
> **Staging green ≠ production ready.**  
> **Repository completeness ≠ commercial validation.**

---

# Current Evidence

## Code / CI baseline

**Current main SHA:** `efd945688419aca74462adf14cb14052e255e61d`

Latest merged repository change:

`docs(saas): correct live staging contract evidence (#543)`

Latest merged functional/code change:

`fix(ci): harden staging endpoint preflight (#538)`

Current main SHA was verified directly from the GitHub repository history as `7d4a04272aac29a48a66822e20fd737876d8a979`.

Post-merge CI for this exact SHA is **NOT YET VERIFIED**: the GitHub workflow-run and combined-status queries currently return no runs/statuses for this commit. Therefore this document does not claim green post-merge CI for the current SHA.

These are repository/CI evidence only; they do **not** prove staging or production readiness.

The latest merged change hardens staging endpoint preflight validation so staging URLs must be bare HTTPS origins without credentials, query strings, or fragments. No live deployment, customer signup, payment, or recovery claim is inferred from repository state.

**Operational evidence not claimed:** live public HTTPS deployment, real signup/onboarding against a deployed environment, live Stripe checkout/customer portal, staging Golden Path, DR restore, and production observability remain unverified unless separately evidenced below.

## Staging

- Project ref: `yebwhcntiockckhdvawt`.
- Exact migration-name audit at current main `7d4a04272aac29a48a66822e20fd737876d8a979`: **64 canonical migration files / 46 live migration rows / 20 literal-name gaps**.
- The 20 literal-name gaps were semantically reconciled against the live staging catalog. **No additional schema gap requiring a new forward-only migration was found.**
- Classification summary:
  - retention controls: **PRESENT_EQUIVALENT**
  - tenant isolation/RLS hardening: **SUPERSEDED_BY_CURRENT_POLICIES**
  - billing workspace-role migrations: **PRESENT_EQUIVALENT**
  - legacy tenant-RLS contract: **SUPERSEDED_BY_WORKSPACE_MEMBERSHIP_MODEL**
  - queue correlation: **PRESENT_EQUIVALENT**
  - commercial entitlements: **PRESENT_EQUIVALENT**
  - dataset registry hardening: **PRESENT_EQUIVALENT** after forward-only feed/retention reconciliation
  - storage registry hardening: **SUPERSEDED_BY_MEMBERSHIP_STORAGE_POLICIES**
  - worker queue consumer: **PRESENT_EQUIVALENT** under historical live migration name `20260928103225_saas_worker_queue_consumer`
  - workspace provisioning: **PRESENT_EQUIVALENT**
  - billing atomic processing/order/team-plan/subscription identity: **PRESENT_EQUIVALENT**
- Verified live objects include `workspace_retention_policy`, `tenant_deletion_tombstone`, `soft_delete_workspace`, `purge_deleted_workspaces`, `entitlement`, `provision_workspace(uuid,text)`, both 9- and 10-argument `process_billing_event()` overloads, `billing_event.provider_event_created_at`, `subscription.last_billing_event_at`, `dataset_version_feed`, `dataset_retention_guard`, `dataset_version_storage_path_contract`, `receive_research_run(integer)`, `ack_research_run(bigint)`, and `subscription_provider_subscription_id_key`.
- Live storage policies are present under `storage.objects` as `qros_datasets_tenant_{insert,select,update,delete}`; legacy `tenant_id` authorization predicates are absent.
- **Do not apply the 20 historical migrations wholesale and do not rewrite migration history.** The remaining migration-name drift is historical/semantic reconciliation, not an unproven missing-SQL claim.
- Real Auth/API Golden Path: **NOT VERIFIED on current main SHA**.
- Two controlled staging identities: **NOT VERIFIED on current main SHA**.
- Staging worker-loss/restart and queue recovery: **NOT VERIFIED on current main SHA**.

## DR

- Recovery target: **NOT PROVISIONED / NOT VERIFIED**
- Recovery S3: **NOT PROVISIONED / NOT VERIFIED**
- DR infrastructure gate: **BLOCKED**
- Full DR drill: **NOT EXECUTED**

---

# Immediate Next Actions

### P0 — Staging database proof
- [x] Complete semantic migration reconciliation: 64 canonical files, 46 live rows, 20 literal-name gaps classified without rewriting history.
- [x] Verify schema, RLS policies, functions, grants and required SaaS constraints against the live staging database; the full `verify_saas_contract.py` contract audit currently passes.
- [ ] Review/document pgtap warning.

### P0 — Staging identity & API
- [ ] Verify two controlled Auth identities.
- [ ] Verify application endpoint.
- [ ] Execute real tenant-isolation API tests.

### P0 — Golden Path
- [ ] Execute Claim → Plan → Dataset → Run → Result → Evidence → Finding.
- [ ] Capture exact SHA and reproducible evidence bundle.

### P1 — DR infrastructure
- [ ] Provision isolated recovery target.
- [ ] Provision dedicated recovery storage.
- [ ] Configure scoped GitHub Environment secrets.
- [ ] Pass the complete DR infrastructure gate.

### P2 — Product
- [ ] Build tenant/workspace UI.
- [ ] Build research workflow UI.
- [ ] Build evidence/audit views.

### P2 — Commercial
- [ ] External-user validation.
- [ ] Paid pilot.
- [ ] Record actual commercial evidence.

---

## Engineering Rules

1. Never claim PASS without the required evidence.
2. Never use production as a substitute for staging or recovery.
3. Never use staging as a substitute for an isolated recovery target.
4. Never expose or commit secrets.
5. Never weaken security, typing, governance or tests to obtain green CI.
6. Never use broad `Any`, blanket ignores or skipped tests as failure suppression.
7. Never fabricate or rewrite migration history to make parity green.
8. Never dispatch destructive/recovery workflows while their gate is blocked.
9. Every release claim must include the exact commit SHA and environment.
10. `BLOCKED`, `NOT_EXECUTED`, and `NOT_VERIFIED` are valid states and must remain explicit.
))`. The complete SaaS contract audit returns all required booleans true and zero legacy `tenant_id` storage policies; the post-reconciliation dataset-feed/storage audit also returns all required feed, retention-guard, storage-contract and storage-policy checks true. `public.dataset_version_storage_path_contract` is present and currently verifies as a CHECK constraint on `public.dataset_version` requiring `tenant/<uuid>/datasets/<sha256>/<positive-version>/`.
- Storage object policies are present under the live names `qros_datasets_tenant_{insert,select,update,delete}`; no legacy `tenant_id` predicate was found. The earlier policy-name-only check must not be interpreted as a storage-policy absence.
- Staging project identity and environment-specific operational state must be re-verified before being presented as current release evidence.
- Historical migration/security observations in this document are retained only as historical evidence unless their current SHA/environment is independently re-verified.
- Real Auth/API Golden Path: **NOT VERIFIED on current main SHA**.
- Two controlled staging identities: **NOT VERIFIED on current main SHA**.
- Staging worker-loss/restart and queue recovery: **NOT VERIFIED on current main SHA**.

## DR

- Recovery target: **NOT PROVISIONED / NOT VERIFIED**
- Recovery S3: **NOT PROVISIONED / NOT VERIFIED**
- DR infrastructure gate: **BLOCKED**
- Full DR drill: **NOT EXECUTED**

---

# Immediate Next Actions

### P0 — Staging database proof
- [ ] Prove canonical migration-history parity.
- [x] Verify schema, RLS policies, functions, grants and required SaaS constraints against the live staging database; the full `verify_saas_contract.py` contract audit currently passes.
- [ ] Review/document pgtap warning.

### P0 — Staging identity & API
- [ ] Verify two controlled Auth identities.
- [ ] Verify application endpoint.
- [ ] Execute real tenant-isolation API tests.

### P0 — Golden Path
- [ ] Execute Claim → Plan → Dataset → Run → Result → Evidence → Finding.
- [ ] Capture exact SHA and reproducible evidence bundle.

### P1 — DR infrastructure
- [ ] Provision isolated recovery target.
- [ ] Provision dedicated recovery storage.
- [ ] Configure scoped GitHub Environment secrets.
- [ ] Pass the complete DR infrastructure gate.

### P2 — Product
- [ ] Build tenant/workspace UI.
- [ ] Build research workflow UI.
- [ ] Build evidence/audit views.

### P2 — Commercial
- [ ] External-user validation.
- [ ] Paid pilot.
- [ ] Record actual commercial evidence.

---

## Engineering Rules

1. Never claim PASS without the required evidence.
2. Never use production as a substitute for staging or recovery.
3. Never use staging as a substitute for an isolated recovery target.
4. Never expose or commit secrets.
5. Never weaken security, typing, governance or tests to obtain green CI.
6. Never use broad `Any`, blanket ignores or skipped tests as failure suppression.
7. Never fabricate or rewrite migration history to make parity green.
8. Never dispatch destructive/recovery workflows while their gate is blocked.
9. Every release claim must include the exact commit SHA and environment.
10. `BLOCKED`, `NOT_EXECUTED`, and `NOT_VERIFIED` are valid states and must remain explicit.
