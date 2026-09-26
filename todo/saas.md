# QROS SaaS TODO / Execution Gate — 2026

Status: **IN PROGRESS — NOT PRODUCTION-READY**

This file is the operational TODO and evidence contract for the QROS SaaS product.

A checkbox is **not** evidence by itself. A task may be marked `[x]` only when implementation and the required verification evidence are actually observed for the relevant commit/environment.

## Evidence status vocabulary

- **PASS** — required implementation/control exists and the required verification evidence was observed.
- **BLOCKED** — work cannot proceed safely because a required external dependency, identity, credential, environment, or authorization is missing.
- **NOT_EXECUTED** — the control exists but the required operational test has not yet been run.
- **NOT_VERIFIED** — evidence is insufficient to claim PASS.
- **EXTERNALLY_PROVISIONED** — the repository documents the requirement, but the resource must be created/configured outside Git.
- **CONFIGURED** — repository-side configuration/contract exists; this does not prove the external resource exists.
- **HISTORICAL** — evidence applies to a prior release/environment and must not be reused as current proof.

---

# 1. Product and research invariants

- [x] Define QROS as a Quant Research Operating System rather than a generic backtester.
- [x] Define Research Claim as a durable research-intent unit.
- [x] Define immutable/content-hashed Research Plan and one-time lock semantics.
- [x] Define evidence lineage and research-governance contracts.
- [x] Publish canonical SaaS product/API contracts.
- [x] Govern AnalysisResult, probability/edge eligibility, calibration, uncertainty, OOS/replication, economic-cost context, and research manifests.
- [x] Preserve the invariant: no predictive/research intelligence claim without validated historical evidence.

---

# 2. Tenant-safe persistence and database security

## 2.1 Tenant boundary

- [x] Workspace/tenant identity is mandatory at SaaS boundaries.
- [x] Ambiguous multi-workspace authentication fails closed.
- [x] Explicit `X-Workspace-ID` selection is supported where applicable.
- [x] Tenant-scoped persistence adapters exist for Research Claim and related SaaS objects.
- [x] Tenant-scoped customer API contracts exist.
- [x] RLS is enabled for QROS tenant-owned public tables.
- [x] Adversarial tenant-isolation tests cover cross-workspace reads/writes/deletes, workspace rebinding, child/parent mismatch, and privileged RPC boundaries.
- [x] Golden Path result/evidence cross-workspace isolation contracts exist.
- [x] Research Claim cross-workspace lookup/pagination isolation coverage exists.

## 2.2 Authentication/session boundary

- [x] Authenticated TenantContext is the authoritative workspace/user boundary.
- [x] JWT role/audience/issuer/UUID subject validation exists.
- [x] Session revocation is checked against the authoritative session store.
- [x] Revoked sessions fail with 401.
- [x] Session-store failure fails closed with 503.
- [x] Server-only session validator is wired in the production composition root.
- [x] Session-validation RPC is restricted to `service_role`, with pinned empty `search_path`.

## 2.3 Migration integrity

- [x] Canonical database migrations are version-controlled under `supabase/migrations/`.
- [x] Migration filename/order/security static checks exist.
- [x] Repository contains 44 canonical migration files at the current SaaS baseline.
- [x] QROS Staging project exists: `yebwhcntiockckhdvawt`, region `ap-northeast-1`, PostgreSQL 17.6/engine 17.
- [x] All 44 repository migration SQL files have been applied to QROS Staging.
- [x] Staging verification observed 44 migration rows, 20 public tables, 0 public tables with RLS disabled, and pgtap installed.
- [ ] **BLOCKED/NOT_VERIFIED:** Prove migration-history identity/canonical parity between repository filenames and the staging migration history. The manual `apply_migration` operation used to provision staging does not by itself prove canonical migration history.
- [ ] Verify required QROS schema objects, constraints, indexes, functions, grants, triggers, and RLS policies against the canonical repository definitions.
- [ ] Do not rewrite or fabricate migration history merely to make the parity check green.

## 2.4 Security advisor / hardening

- [ ] Review the current staging Security Advisor findings.
- [ ] Decide explicitly whether pgtap being installed in `public` is acceptable for the staging contract; do not silently suppress the warning.
- [ ] Resolve or document applicable Auth configuration hardening findings.
- [x] No production credential values, JWTs, service-role keys, or AWS credentials are committed to the repository.

---

# 3. Dataset and artifact storage

- [x] Tenant-scoped object-storage abstraction.
- [x] Content-addressed artifacts.
- [x] Upload/download authorization.
- [x] Dataset version registry.
- [x] Reproducibility manifest generation.
- [x] Dataset version path input validation is explicit and fail-closed.
- [ ] Retention/deletion policy operational enablement.
- [x] Retention eligibility contract.
- [x] Destructive retention executor with durable state binding, dependency resolution, audit events, and recovery transitions.
- [ ] Production destructive retention remains disabled until operational release gate passes.
- [ ] Verify storage recovery against an isolated recovery target.

---

# 4. Durable execution

- [x] Idempotency keys with atomic durable reservation.
- [x] Durable job records and state transitions.
- [x] Bounded retry policy and explicit terminal states.
- [x] Worker heartbeat/lease semantics.
- [x] Provenance-linked job outputs.
- [ ] Execute staging worker-loss/restart recovery drill.
- [ ] Execute queue/job recovery drill against isolated non-production infrastructure.
- [ ] Verify recovery evidence and state transitions.

---

# 5. API productization

- [x] Stable versioned API surface.
- [x] Request validation and size limits.
- [x] Authorization policy matrix.
- [x] Rate limiting and abuse controls.
- [x] Pagination/filter/sort contracts.
- [x] Structured error model.
- [x] Idempotent research-run mutation semantics.
- [x] Request-correlation metadata.
- [ ] Complete staging end-to-end API verification using real staging Auth identities.
- [ ] Verify two distinct non-production user/workspace identities can exercise the intended tenant boundary.
- [ ] Verify cross-tenant access fails closed through the real application/API path, not only unit tests.

---

# 6. Research services and governance

- [x] Deterministic computational path planner v1.
- [x] Immutable planner output/hash contract.
- [x] Governed AnalysisResult bound to planner output.
- [x] Probability/edge service registry.
- [x] Calibration and uncertainty outputs.
- [x] Calibration sample evidence bound to governed edge eligibility.
- [x] Holm/Benjamini-Hochberg multiple-testing correction primitives.
- [x] Multiple-testing results enforced at governed edge eligibility.
- [x] OOS/replication state tracking.
- [x] Economic cost/slippage context bound to governed edge eligibility.
- [x] Deterministic research artifact manifests.
- [ ] Complete one full staging governed research workflow from Claim → Plan → Experiment/Run → Result → Evidence → Validation/Finding.
- [ ] Verify the workflow against real staging persistence and authorization.

---

# 7. Product UI

- [ ] Tenant/workspace shell.
- [ ] Claim creation and plan-lock workflow.
- [ ] Experiment/run/result explorer.
- [ ] Evidence lineage graph view.
- [ ] Validation/finding/replication status views.
- [x] Deterministic governed research report export API.
- [ ] Audit trail UI.

---

# 8. Billing and commercial controls

- [ ] Plan/entitlement model.
- [ ] Usage metering.
- [ ] Billing-provider adapter.
- [ ] Subscription lifecycle handling.
- [ ] Grace-period and failed-payment states.
- [ ] Entitlement enforcement independent of UI.
- [ ] Paid pilot offer tied to a concrete research deliverable.
- [ ] Obtain external-user validation.
- [ ] Record user feedback and failure modes without weakening governance.
- [ ] Treat payment/repeat usage/qualified pilot commitment as commercial evidence; repository completeness is not commercial evidence.

---

# 9. Observability and security hardening

- [ ] Structured application logs.
- [ ] API metrics and traces.
- [ ] Durable-job metrics and traces.
- [ ] Security-sensitive audit events.
- [ ] Secret/config validation.
- [ ] Dependency scanning.
- [ ] Container/image scanning.
- [ ] Threat-model review/update.
- [x] Tenant-isolation red-team tests.
- [ ] Production observability acceptance test.
- [ ] Verify no secrets/credential-bearing URLs appear in logs or evidence artifacts.

---

# 10. Disaster Recovery — infrastructure gate

## 10.1 Repository-side contract

- [x] DR source authorization is explicit and fail-closed.
- [x] Production is rejected as a backup source for the governed DR drill.
- [x] Restore target must be disposable/isolated.
- [x] DR evidence manifest distinguishes PASS / NOT_EXECUTED / NOT_RECORDED.
- [x] DR infrastructure contract is version-controlled.
- [x] DR secret contract documents required secret names without secret values.
- [x] Release caller binds source environment and release SHA.
- [x] DR documentation separates Git-controlled contracts from externally provisioned infrastructure.

## 10.2 External infrastructure

**Current gate: BLOCKED until every required item is independently verified.**

Required source:
- [x] Authoritative non-production staging source exists: QROS Staging / `yebwhcntiockckhdvawt`.
- [ ] Record authoritative staging database identity.
- [ ] Record source release SHA actually deployed to staging.
- [ ] Prove source is non-production and not the production database.

Required recovery target:
- [ ] Dedicated isolated recovery PostgreSQL/Supabase target exists.
- [ ] Recovery target has independent identity.
- [ ] Recovery target is not staging.
- [ ] Recovery target is not production.
- [ ] Recovery target PostgreSQL major is compatible.
- [ ] Recovery target can execute migration, RLS, tenant-isolation, and integrity verification.

Required recovery storage:
- [ ] Dedicated recovery S3 bucket/namespace exists.
- [ ] Recovery storage region is recorded.
- [ ] Recovery credentials are scoped to the recovery operation.
- [ ] Production bucket is not used as the recovery target.

Required staging application/auth:
- [ ] `QROS_STAGING_BASE_URL` exists.
- [ ] Staging JWT test identity exists.
- [ ] Independent isolation-test identity exists.
- [ ] Operator authorization exists.
- [ ] Evidence retention location exists.

Required GitHub staging/recovery secrets must exist **without exposing their values**:
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

**Rule:** the infrastructure gate is PASS only when all required source, target, storage, auth, authorization, secret-presence, and evidence-retention checks pass. Missing/unknown/unverified = BLOCKED.

---

# 11. Disaster Recovery execution

Do not dispatch recovery workflows until the infrastructure gate above is PASS.

- [ ] Run controlled backup from authorized staging source.
- [ ] Verify backup artifact integrity.
- [ ] Restore into the isolated recovery target.
- [ ] Apply/verify canonical repository migrations.
- [ ] Verify PostgreSQL major compatibility.
- [ ] Verify required QROS tables/constraints/functions/indexes/grants.
- [ ] Verify RLS is enabled and policies are correct.
- [ ] Verify tenant isolation with independent identities.
- [ ] Verify critical record counts.
- [ ] Verify dataset-version identity/content-addressing invariants.
- [ ] Verify object-storage recovery.
- [ ] Verify worker/queue recovery.
- [ ] Verify application health/readiness.
- [ ] Generate immutable DR evidence manifest.
- [ ] Record actual RPO.
- [ ] Record actual RTO.
- [ ] Record failures and remediation; never convert NOT_EXECUTED to PASS.
- [ ] Publish operational DR runbook from observed results.

---

# 12. Staging Golden Path

**Current status: NOT EXECUTED / BLOCKED by missing verified staging Auth/application identities and incomplete migration-history parity.**

Required sequence:

1. [ ] Verify staging project identity.
2. [ ] Verify staging release SHA.
3. [ ] Verify canonical migration parity.
4. [ ] Verify staging Auth identities.
5. [ ] Verify application endpoint.
6. [ ] Create/seed only controlled non-production test data.
7. [ ] Execute Claim → Plan lock → Dataset → Experiment/Run → Result → Evidence → Finding flow.
8. [ ] Verify tenant isolation with two identities.
9. [ ] Verify authorization failures.
10. [ ] Verify idempotency/retry/lease behavior.
11. [ ] Verify provenance/content hashes.
12. [ ] Verify structured errors and correlation metadata.
13. [ ] Capture exact commit SHA and CI evidence.
14. [ ] Produce staging Golden Path evidence bundle.

---

# 13. Production readiness

Production readiness requires all applicable gates below to be independently evidenced:

1. Research invariants PASS.
2. Unit/integration/security tests PASS.
3. Tenant isolation PASS.
4. Canonical schema/migration parity PASS.
5. Authentication/session boundary PASS.
6. Authorization matrix PASS.
7. Evidence lineage integrity PASS.
8. Idempotency and durable jobs PASS.
9. Backup/restore PASS.
10. Object-storage recovery PASS.
11. Queue/worker recovery PASS.
12. Observability live and verified.
13. Security hardening reviewed.
14. Exact-release CI PASS.
15. Release artifact reproducible and versioned.
16. No known high-severity security or data-integrity defect remains open.
17. Staging Golden Path PASS.
18. Production Golden Path PASS.
19. Commercial validation is recorded separately from engineering readiness.

**Important:** Passing repository CI does not prove staging/production operational readiness. Passing staging does not prove production readiness. Commercial validation is not inferred from code completeness.

---

# 14. Current exact evidence baseline

## Code baseline

Current known SaaS fix baseline:

`6263fb25d19175595ff51e495a80e35270ae117e`

Commit:
`fix(saas): validate dataset version path inputs`

Observed validation:
- Full pytest: 3002 passed, 9 skipped, 1 warning.
- SaaS tests: 221 passed, 1 skipped.
- Ruff: PASS.
- Mypy: PASS.
- Property-based tests: PASS.
- Python 3.11/3.12: PASS.
- Quant Engine: PASS.
- Health Evidence: PASS.
- Supabase Security: PASS.
- Release Readiness: PASS.
- Affected dataset-version storage-path test: PASS.

Local Windows validation from the GitHub/Supabase execution environment: **NOT_EXECUTED**. Do not claim it was run locally.

## CI evidence

Latest exact-SHA CI evidence observed for the current fix baseline:
- CI #2576 / run `36225256675`: SUCCESS.
- PR CI #2577 / run `36225258453`: SUCCESS.
- Supabase Security #831: SUCCESS.
- Release Readiness #710: SUCCESS.

## Staging infrastructure evidence

- Project: **QROS Staging**
- Project ref: `yebwhcntiockckhdvawt`
- Region: `ap-northeast-1`
- PostgreSQL: `17.6.1` / engine 17
- Status observed: ACTIVE_HEALTHY
- Repository migration SQL files applied: 44/44
- Observed migration rows: 44
- Observed public tables: 20
- Observed public tables with RLS disabled: 0
- pgtap: installed
- Migration-history canonical identity: **NOT_VERIFIED**
- Real staging Auth/application Golden Path: **NOT_EXECUTED**
- Recovery target: **NOT_PROVISIONED / BLOCKED**
- Recovery S3: **NOT_PROVISIONED / BLOCKED**
- Full DR drill: **NOT_EXECUTED / BLOCKED**

---

# 15. Execution rules

1. Never mark a task PASS from code inspection alone when operational evidence is required.
2. Never use production as a substitute for staging or recovery.
3. Never use staging as a substitute for an isolated recovery target.
4. Never expose or commit secrets.
5. Never weaken a security test, RLS policy, type contract, or governance invariant to obtain green CI.
6. Never add `Any`, broad casts, blanket ignores, or skipped tests solely to suppress failures.
7. Never fabricate migration history.
8. Never rewrite migration metadata merely to make a parity check pass.
9. Never dispatch destructive/recovery workflows while the infrastructure gate is BLOCKED.
10. Every release claim must identify the exact commit SHA and relevant environment.
11. `NOT_EXECUTED`, `NOT_VERIFIED`, and `BLOCKED` are valid final states; they must not be silently converted to PASS.
12. Repository completeness is engineering evidence, not proof of production operation or commercial demand.

---

# 16. Immediate next actions

### Priority A — staging schema identity
- [ ] Establish canonical migration-history parity for all 44 migrations.
- [ ] Verify actual staging schema/policies/functions/grants against repository expectations.
- [ ] Resolve/document the pgtap public-schema warning.

### Priority B — staging authentication
- [ ] Provision/verify two controlled non-production Auth identities.
- [ ] Verify staging application endpoint.
- [ ] Verify workspace memberships and authorization.
- [ ] Run real API tenant-isolation tests.

### Priority C — staging Golden Path
- [ ] Execute the complete governed research workflow.
- [ ] Capture exact SHA, environment identity, test identities, outputs, and evidence hashes.

### Priority D — DR infrastructure
- [ ] Provision isolated recovery target.
- [ ] Provision dedicated recovery S3 storage.
- [ ] Configure scoped GitHub Environment secrets.
- [ ] Verify all 12 infrastructure-gate criteria.
- [ ] Only then dispatch the DR workflow.

### Priority E — commercial validation
- [ ] Complete one narrow customer workflow.
- [ ] Obtain external-user validation.
- [ ] Define a paid pilot around a concrete research deliverable.
- [ ] Record actual commercial evidence separately from technical readiness.
