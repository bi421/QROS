# ResearchOS SaaS — Production Roadmap / TODO

**Status:** ACTIVE
**Branch:** `feat/saas-production-foundation`
**Rule:** scientific/research semantics remain separate from SaaS delivery concerns.

This is the authoritative implementation checklist for turning ResearchOS into a production-grade multi-tenant SaaS. Each phase must be implemented, tested, and verified before the next phase is marked complete.

## Definition of production-grade

A phase is not complete because code exists. It is complete only when:

- implementation is present in the repository;
- automated tests cover the new behavior and failure modes;
- security boundaries are explicitly tested;
- CI executes the relevant tests;
- documentation/configuration matches the implementation;
- deployment/rollback behavior is defined where applicable;
- no scientific-result contract changes were introduced unintentionally;
- verification evidence is recorded in this file.

## Phase 0 — Baseline and architecture freeze

- [ ] Inventory existing `researchos/saas` implementation.
- [ ] Define SaaS/application boundary versus scientific/research core.
- [ ] Define supported workflows and explicitly reject unsupported workflows.
- [ ] Define API versioning policy (`/v1`).
- [ ] Define tenant/workspace ownership model.
- [ ] Define production environment matrix: local, CI, staging, production.
- [ ] Define data classification: public, tenant data, research artifacts, secrets, operational logs.
- [ ] Capture baseline test/coverage/health evidence.
- [ ] Freeze scientific calculation contracts while SaaS work proceeds.

## Phase 1 — Application foundation

- [ ] Production application factory and dependency injection.
- [ ] Configuration/settings object with environment validation.
- [ ] Fail-closed startup for missing production-critical configuration.
- [ ] Structured logging.
- [ ] Request/correlation IDs.
- [ ] Standard error envelope.
- [ ] API versioning and OpenAPI metadata.
- [ ] Health/readiness/liveness semantics.
- [ ] Graceful shutdown and worker lifecycle contracts.
- [ ] Deterministic UTC time handling.

## Phase 2 — Identity and multi-tenancy

- [ ] Supabase Auth integration.
- [ ] JWT/session validation.
- [ ] Workspace membership model.
- [ ] Roles/permissions model.
- [ ] Server-side authorization independent of client metadata.
- [ ] Tenant isolation on every tenant-owned query.
- [ ] PostgreSQL RLS on exposed tenant tables.
- [ ] Negative cross-tenant access tests.
- [ ] Session/token security policy.
- [ ] Account/workspace lifecycle: create, invite, suspend, delete.

## Phase 3 — Persistence and data model

- [ ] Production PostgreSQL schema.
- [ ] Versioned migrations.
- [ ] Tenant/workspace tables.
- [ ] Membership/role tables.
- [ ] Research run/job table.
- [ ] Dataset metadata table.
- [ ] Research artifact metadata table.
- [ ] Usage counters/ledger.
- [ ] Audit event table.
- [ ] Idempotency-key table/state.
- [ ] Billing/customer/subscription mapping.
- [ ] Appropriate indexes and constraints.
- [ ] Foreign-key and deletion semantics.
- [ ] RLS policies and policy tests.
- [ ] Backup/restore procedure.

## Phase 4 — Research execution platform

- [ ] Durable job queue abstraction.
- [ ] Worker process separated from HTTP request lifecycle.
- [ ] Job state machine with valid transitions only.
- [ ] Idempotent job submission.
- [ ] Retry policy with bounded attempts.
- [ ] Dead-letter/failure handling.
- [ ] Cancellation semantics.
- [ ] Per-tenant concurrency limits.
- [ ] Monthly usage limits.
- [ ] Dataset size limits.
- [ ] Resource/time limits.
- [ ] Worker heartbeat/lease handling.
- [ ] Persisted execution metadata.
- [ ] Reproducible research execution metadata: workflow/version/input/artifact hashes.

## Phase 5 — Data and artifact storage

- [ ] Supabase Storage/object storage integration.
- [ ] Private buckets by default.
- [ ] Tenant-scoped storage paths.
- [ ] Signed URL access with bounded expiry.
- [ ] Upload validation and size limits.
- [ ] Content-type validation.
- [ ] Artifact checksum/content-addressing strategy.
- [ ] Retention policy.
- [ ] Deletion policy.
- [ ] Storage lifecycle/cleanup jobs.
- [ ] Cross-tenant storage isolation tests.

## Phase 6 — API hardening

- [ ] Authentication on every non-public endpoint.
- [ ] Authorization on every tenant resource.
- [ ] Input validation and bounded payloads.
- [ ] Rate limiting.
- [ ] Idempotency for mutation endpoints.
- [ ] Pagination for collection endpoints.
- [ ] Filtering/sorting allowlists.
- [ ] Consistent HTTP status/error semantics.
- [ ] Request size/time limits.
- [ ] CORS policy.
- [ ] Security headers.
- [ ] OpenAPI contract tests.
- [ ] API compatibility tests.
- [ ] Abuse/negative tests.

## Phase 7 — Billing and monetization

- [ ] Product/plan catalog.
- [ ] Free/Pro/Team/Enterprise entitlement model.
- [ ] Stripe integration or selected billing provider adapter.
- [ ] Customer mapping.
- [ ] Subscription lifecycle.
- [ ] Checkout/customer portal flow.
- [ ] Webhook signature verification.
- [ ] Webhook idempotency.
- [ ] Entitlement synchronization.
- [ ] Failed-payment handling.
- [ ] Cancellation/grace-period behavior.
- [ ] Usage metering.
- [ ] Plan enforcement server-side.
- [ ] Billing audit trail.
- [ ] No payment secrets in client code.

## Phase 8 — Frontend/product UX

- [ ] Production web application shell.
- [ ] Sign up/sign in/sign out.
- [ ] Workspace switcher.
- [ ] Dashboard.
- [ ] Dataset management UI.
- [ ] Research run creation UI.
- [ ] Job progress/status UI.
- [ ] Result/artifact viewer.
- [ ] Usage/billing page.
- [ ] Team/member management.
- [ ] Account/settings page.
- [ ] Error/empty/loading states.
- [ ] Accessible keyboard/navigation behavior.
- [ ] Responsive desktop/mobile layout.
- [ ] Product analytics with privacy boundaries.

## Phase 9 — Observability and operations

- [ ] Structured JSON logs.
- [ ] Metrics.
- [ ] Distributed/request tracing where justified.
- [ ] Job latency/error metrics.
- [ ] Queue depth metrics.
- [ ] Per-tenant usage metrics without leaking tenant data.
- [ ] Billing/webhook failure metrics.
- [ ] Alert thresholds.
- [ ] Operational dashboards.
- [ ] Incident runbook.
- [ ] On-call/escalation procedure.
- [ ] Audit-log retention.

## Phase 10 — Security engineering

- [ ] Threat model.
- [ ] Authentication threat review.
- [ ] Authorization/BOLA/IDOR tests.
- [ ] RLS review.
- [ ] Storage access review.
- [ ] Secrets management.
- [ ] Dependency pinning and lockfiles.
- [ ] Dependency vulnerability scanning.
- [ ] Secret scanning.
- [ ] SAST/lint/type checks.
- [ ] Container/image scanning if containers are used.
- [ ] SSRF/file-upload/path-traversal review.
- [ ] SQL injection review.
- [ ] Rate-limit/abuse review.
- [ ] Security headers/CORS review.
- [ ] Production debug mode disabled.
- [ ] Least-privilege service credentials.
- [ ] Security incident response procedure.

## Phase 11 — Reliability, deployment, and disaster recovery

- [ ] Reproducible production build.
- [ ] Staging environment.
- [ ] Production environment.
- [ ] CI gates for application, migration, security, and tests.
- [ ] Deployment automation.
- [ ] Migration safety checks.
- [ ] Rollback strategy.
- [ ] Zero/low-downtime deployment strategy where applicable.
- [ ] Database backup verification.
- [ ] Restore drill.
- [ ] RPO/RTO targets.
- [ ] Worker recovery after crash.
- [ ] Queue recovery after outage.
- [ ] Dependency outage behavior.
- [ ] Graceful degradation.

## Phase 12 — Testing and quality gates

- [ ] Unit tests.
- [ ] Integration tests.
- [ ] API contract tests.
- [ ] Database/RLS integration tests.
- [ ] Auth tests.
- [ ] Cross-tenant isolation tests.
- [ ] Billing/webhook tests.
- [ ] Worker/job lifecycle tests.
- [ ] Storage tests.
- [ ] End-to-end smoke tests.
- [ ] Failure/retry tests.
- [ ] Load/performance tests.
- [ ] Migration tests.
- [ ] Deterministic reproducibility tests.
- [ ] Scientific regression suite remains green.
- [ ] Coverage measured for SaaS-critical modules.

## Phase 13 — Documentation and customer readiness

- [ ] Public product documentation.
- [ ] API documentation.
- [ ] Authentication guide.
- [ ] Workspace/team guide.
- [ ] Research workflow guide.
- [ ] Data/privacy documentation.
- [ ] Billing/plan documentation.
- [ ] Terms of service.
- [ ] Privacy policy.
- [ ] Data retention/deletion policy.
- [ ] Security contact/reporting process.
- [ ] Status/incident communication process.
- [ ] Customer support workflow.
- [ ] Release/versioning policy.

## Phase 14 — Production launch gate

- [ ] All P0/P1 security issues closed.
- [ ] All tenant-isolation tests pass.
- [ ] Production migration rehearsal passes.
- [ ] Backup restore verified.
- [ ] Monitoring/alerts verified.
- [ ] Billing lifecycle verified end-to-end.
- [ ] Authentication lifecycle verified end-to-end.
- [ ] Research job lifecycle verified end-to-end.
- [ ] API smoke tests pass in staging.
- [ ] Performance baseline recorded.
- [ ] Rollback drill passes.
- [ ] No unresolved critical scientific regression.
- [ ] Release candidate tagged.
- [ ] Production launch evidence recorded.

## Implementation order

1. Baseline + architecture freeze
2. Application foundation
3. Identity + tenancy
4. Database + RLS
5. Durable jobs/workers
6. Storage/artifacts
7. API hardening
8. Billing
9. Frontend/product UX
10. Observability
11. Security hardening
12. Deployment/DR
13. Full test/quality gates
14. Documentation/customer readiness
15. Production launch gate

## Evidence ledger

| Phase | Status | Evidence | Notes |
|---|---|---|---|
| 0 | IN PROGRESS | | |
| 1 | NOT STARTED | | |
| 2 | NOT STARTED | | |
| 3 | NOT STARTED | | |
| 4 | NOT STARTED | | |
| 5 | NOT STARTED | | |
| 6 | NOT STARTED | | |
| 7 | NOT STARTED | | |
| 8 | NOT STARTED | | |
| 9 | NOT STARTED | | |
| 10 | NOT STARTED | | |
| 11 | NOT STARTED | | |
| 12 | NOT STARTED | | |
| 13 | NOT STARTED | | |
| 14 | NOT STARTED | | |
