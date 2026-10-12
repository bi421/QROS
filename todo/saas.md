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
| Database migrations | 🟡 Blocked (current release evidence pending) | The last recorded audit observed 64 canonical migration files and 46 staging migration rows with historical aliases. This is a historical snapshot, not proof of schema/migration parity for the current deployed release; rerun the environment-specific audit and bind its artifact to the deployed SHA. |
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

- [x] Historical canonical-vs-live migration-name audit recorded 64 canonical files, 46 live rows and 20 literal-name gaps; semantic reconciliation reported no additional missing schema behavior. This is historical evidence and must be revalidated against the current deployed release.
- [ ] Re-run staging schema/security and migration reconciliation against the current deployed release SHA; prior semantic reconciliation is historical evidence only.
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
- [x] Historical snapshot A recorded 45 migration rows; the worker migration appeared under its historical remote display name.
- [x] A later historical audit recorded 46 staging migration rows and 20 literal-name gaps across 64 canonical files. These counts are from different observations and must not be combined as one current snapshot.
- [ ] Re-run a single canonical migration-history and schema audit against the verified current staging deployment SHA. Confirm the live row count, aliases, all canonical names, and the `dataset_version_feed` schema contract. Do not rewrite migration history to force name parity.
- [x] 23 public tables observed.
- [x] 23/23 public tables have RLS enabled; 0 disabled.

### Remaining
- [x] Verify the worker execution version `20260928103556` is present; its historical remote display name remains `20260928103225_saas_worker_queue_consumer` and is not rewritten.
- [x] Historical review recorded 23 public tables with RLS enabled (23/23, 0 disabled); current state has not been re-verified against a deployment SHA.
- [x] Historical review covered public policies/triggers, governed queue-function grants, Security Advisor findings, and the existing `pgtap`-in-public-schema warning; no live schema mutation was performed in that review.
- [ ] Re-run and retain current staging evidence for RLS, policies, triggers, grants, Security Advisor findings, and migration/schema parity, all bound to the verified staging deployment SHA.

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

# Current Evidence — refreshed 2026-10-12

## Exact repository baseline

- **Repository:** `bi421/QROS`
- **Previous roadmap baseline:** `3572a66360e00e6b5f5c36752d9734d6df185c93` (PR #670 merge; the prior roadmap incorrectly continued to call this current).
- **Audit baseline requested:** `40315d796f46ff4ec5b83b9811dae978c176c2af`.
- **Current `main` SHA:** `1b2fac61062a9d90546ed399e489cae4f080a4dd`.
- **Exact ref proof:** comparing `1b2fac61062a9d90546ed399e489cae4f080a4dd` to `main` returned `identical` (0 ahead / 0 behind). Comparing `40315d796f46ff4ec5b83b9811dae978c176c2af` to `main` returned `ahead`, 110 commits, 0 behind.
- **Latest main commit:** [`1b2fac61062a9d90546ed399e489cae4f080a4dd`](https://github.com/bi421/QROS/commit/1b2fac61062a9d90546ed399e489cae4f080a4dd), `fix(staging): canonicalize host comparison against production (#711)`.
- **File blob before this refresh:** `498ff68893935ba1cd9e270e84a8fc8e77f9e827`.
- This section records repository state, not a claim that the running deployment uses this SHA.

## Exact-SHA CI evidence

**Current main SHA at this audit: `1221cea820bf7e9b8a61be9b9b7750cd0020f7bb` — CI NOT YET VERIFIED GREEN.**

- GitHub branch API confirms `main` points to this exact SHA and reports branch protection disabled.
- Git Governance run [#770](https://github.com/bi421/QROS/actions/runs/38203377336) completed successfully on this SHA.
- CI run [#4240](https://github.com/bi421/QROS/actions/runs/38203377331) was still pending at audit time. Do not mark exact-SHA CI green until this run completes successfully.
- Previous main SHA `1b2fac61062a9d90546ed399e489cae4f080a4dd` has CI run [#4239](https://github.com/bi421/QROS/actions/runs/38202928115) still in progress at audit time; completed checks observed on that exact SHA were successful, but the full configured test suite + coverage job had not completed. Git Governance run [#769](https://github.com/bi421/QROS/actions/runs/38202927987) succeeded on that SHA.
- Commit-status API returning zero legacy statuses is not evidence that GitHub Actions checks are absent; inspect the Actions/check-runs endpoints tied to the exact SHA.
- Even successful CI does not prove deployed runtime, live Auth, migration execution, backup/restore, billing, or commercial readiness.

## CI evidence for the roadmap PR

- **Current roadmap PR commit checked:** `b448f6c61ea65463e5f732897c21941ea6a10a61` (superseded PR #717 head; its PR-triggered CI and Git Governance runs completed successfully, but the branch became diverged after `main` advanced).
- **CI run:** [#4233](https://github.com/bi421/QROS/actions/runs/38201833618) — `success`.
- **Git Governance run:** [#768](https://github.com/bi421/QROS/actions/runs/38201833706) — `success`.
- These runs validate only that exact documentation-branch commit. They do not prove CI for current `main` SHA `1b2fac61062a9d90546ed399e489cae4f080a4dd`, and they do not prove staging or production behavior.

## Changes since the requested baseline — PRs #685–#711

The current `main` history includes the following workstreams. These are repository/code changes; they are not substitutes for live operational evidence.

### Market-memory and probability correctness — #685–#696

- #685–#687: guard conditional/bootstrap and OOS mean arithmetic against overflow; make finite-sample means safer; make OOS success probability direction-aware.
- #688: recorded as a redundant/diverged attempt, not a separate delivered feature.
- #689–#692: dependence-aware probability intervals, including moving-block bootstrap and effective-sample-size handling.
- #693: align walk-forward OOS validation with the dependence-CI API.
- #694–#696: reject non-finite matched OOS outcomes, boolean outcomes, and empty label-boundary partitions; fail closed on invalid evidence rather than silently dropping it.
- #697–#699: stabilize the quant backend/test import path; reject undersized simulations; expose pytest pipeline failures and align tests with the fail-closed contract.

### Git hygiene — #700

- #700 (`7d510cb911ab59ec4fe4a4327aed57b7261bbe1b`) is **not part of current main** at this evidence snapshot. Commit comparison reports the PR branch and main as diverged: main is 12 commits ahead of the shared base, while the PR head is 1 commit ahead. Do not describe its `.gitignore` change as delivered or merged. Its current PR state/checks must be verified separately before any merge decision.

### Staging Golden Path and recovery controls — #701–#711

- #701–#702: align Golden Path stage/progress checks and accept the documented paginated dataset-version response envelope.
- #703–#705: isolate recovery objects by workflow run, restore drill objects into a separate recovery Supabase target, persist/validate tenant-isolation evidence from paginated API responses.
- #706–#707: preserve machine-readable restore-failure evidence and emit valid JSON failure reports.
- #708–#709: restrict recovery object-key characters and reject production projects as recovery targets.
- #710–#711: reject production hosts in the staging Golden Path gate and normalize hostnames before comparing staging versus production.
- These changes harden workflow safeguards. They do **not** prove that a real staging Golden Path or isolated recovery drill has passed.

## SaaS implementation status

Implemented in the repository source tree (implementation evidence only):

- Public `/onboarding` surface and Supabase signup/signin integration.
- Authenticated `POST /v1/workspaces` provisioning path, owner membership and FREE subscription.
- `/v1/me` customer identity surface.
- Dataset → immutable version → governed research-run path.
- Stripe billing adapter and webhook lifecycle; billing fails closed if the webhook secret is absent.

These do not establish a deployed, externally accessible, paid customer path.

## Current external gates

| Gate | Current evidence status | What is still required |
|---|---|---|
| Exact-SHA CI | **PENDING / NOT VERIFIED GREEN** for current main `1221cea820bf7e9b8a61be9b9b7750cd0020f7bb`; prior `1b2fac61062a9d90546ed399e489cae4f080a4dd` suite also incomplete at audit | Wait for CI run #4240 on current main to finish; then record conclusion and SHA |
| Staging migration/schema parity | **NOT VERIFIED for current deployed release SHA** | Re-run canonical migration/schema/security audit and retain its artifact |
| Staging identities and API | **NOT VERIFIED** | Two controlled identities; real endpoint; tenant isolation and authorization-failure evidence |
| Staging Golden Path | **NOT VERIFIED** | Run the 13-stage gate against a verified non-production hostname; retain run URL/artifacts and exact SHA |
| Production-host exclusion | Implemented in workflow commits #710–#711; **live execution NOT VERIFIED** | Successful staging gate run demonstrating the production-host guard |
| Production backup | **BLOCKED** in the last observed scheduled run | Configure approved `BACKUP_AWS_ROLE_ARN` repository variable / AWS OIDC role, then verify backup, checksum and remote manifest evidence |
| Isolated DR | **NOT VERIFIED / BLOCKED** | Prove source is staging; provision a separate recovery project and storage; pass infrastructure gate before dispatch |
| Restore drill / RPO / RTO | **NOT EXECUTED / NOT VERIFIED** | Successful isolated restore, integrity/security checks and measured RPO/RTO evidence |
| Public HTTPS deployment | **NOT VERIFIED** | Public endpoint, TLS and exact deployed release SHA |
| Live Supabase Auth | **NOT VERIFIED** | Signup/email-confirmation and real authenticated API path on deployed infrastructure |
| Live Stripe | **NOT VERIFIED** | Provider checkout/portal/webhook delivery with evidence |
| Observability acceptance | **NOT VERIFIED** | Production telemetry, alerts and credential-redaction acceptance evidence |
| Product UI | **NOT COMPLETE** | Tenant/workspace, research workflow, evidence lineage and audit UI |
| Customer/commercial validation | **NOT VERIFIED** | External user, measurable outcome, paid pilot or qualified commitment |

Historical staging details (including the previously observed project reference, migration counts, RLS counts and Security Advisor findings) must not be treated as current release proof until rechecked against the target environment and its deployed SHA. No staging/production/recovery environment identity is inferred from a repository commit.

## Immediate next actions

### P0 — exact release evidence
1. Verify required GitHub Actions workflows against current main SHA `1221cea820bf7e9b8a61be9b9b7750cd0020f7bb`; wait for CI run #4240 to finish and record workflow names, run IDs, conclusion and SHA.
2. Verify which deployed environment, if any, runs that exact SHA.
3. Re-run staging migration/schema/RLS/policy/function/grant checks against the verified staging environment; attach the reproducible audit artifact.
4. Configure the approved `BACKUP_AWS_ROLE_ARN` / AWS OIDC dependency without exposing credentials, then rerun the backup workflow and inspect checksum plus remote-manifest evidence.

### P0 — staging Golden Path
1. Verify the staging base URL is genuinely non-production and configure the required staging environment secrets.
2. Verify two distinct controlled Auth identities.
3. Run the Golden Path gate and capture its run URL, exact SHA, result, and artifacts. A hardened workflow alone is not a pass.

### P1 — recovery
1. Verify source identity is staging, and provision an independent recovery Supabase/PostgreSQL target and recovery storage.
2. Pass the DR infrastructure gate before dispatching the drill.
3. Run backup/restore, validate schema/security/RLS/tenant isolation and objects, and measure actual RPO/RTO.

### P2 — product and commercial
1. Build the missing tenant/workspace, research workflow and evidence/audit UI.
2. Validate one complete governed workflow with an external user.
3. Record real paid-pilot/payment/repeat-use evidence; do not infer commercial readiness from code completion.

## Engineering Rules

1. Never claim PASS without the required evidence.
2. Every release claim must include the exact commit SHA and environment.
3. Separate **IMPLEMENTED**, **PROVEN**, and **EXTERNAL DEPENDENCY**.
4. Never use production as a substitute for staging or recovery.
5. Never use staging as a substitute for an isolated recovery target.
6. Never expose or commit secrets.
7. Never weaken security, typing, governance or tests to obtain green CI.
8. Never fabricate or rewrite migration history to make parity green.
9. Never dispatch destructive/recovery workflows while their gate is blocked.
10. `BLOCKED`, `NOT_EXECUTED`, and `NOT_VERIFIED` are valid states and must remain explicit.

---
