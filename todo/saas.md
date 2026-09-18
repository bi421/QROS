# QROS SaaS Implementation Plan — 2026

Status: **IN PROGRESS**

This file is the execution contract for turning QROS into a research-grade multi-tenant SaaS. A feature is not considered complete until implementation, tests, integration, security, and CI verification are all observed.

## Phase 0 — Product and research invariants
- [x] Define QROS as a Quant Research Operating System, not a generic backtester.
- [x] Define Research Claim as the durable unit of research intent.
- [x] Define immutable/content-hashed Research Plan and one-time lock semantics.
- [x] Define evidence lineage and research-governance contracts.
- [x] Publish a single canonical SaaS product specification and API contract.

## Phase 1 — Evidence graph integration
- [x] Add Research Claim domain model.
- [x] Add Research Plan content hash and one-time lock.
- [x] Add claim persistence adapter.
- [x] Add governed Claim → Plan → existing immutable Evidence projection.
- [x] Reject evidence references that do not exist.
- [x] Require a locked plan before evidence attachment.
- [x] Add regression tests for the claim/evidence bridge.
- [ ] Connect graph projection to Experiment/Run/Result/Validation/Finding traversal APIs.
- [ ] Add first-class contradiction/replication edges without mutating historical artifacts.
- [ ] Add graph integrity and orphan detection gate.

## Phase 2 — Tenant-safe persistence
- [ ] Make workspace/tenant identity mandatory at every SaaS boundary.
- [ ] Implement canonical Supabase persistence adapters.
- [ ] Enforce RLS for every tenant-owned table.
- [ ] Add tenant-isolation integration tests.
- [ ] Add migration/version compatibility checks.

## Phase 3 — Durable execution
- [x] Introduce idempotency keys for research-run mutation with atomic durable reservation.
- [x] Add durable job records and state transitions.
- [ ] Add retry policy with bounded attempts and explicit terminal states.
- [x] Add worker heartbeat/lease semantics.
- [ ] Ensure every job output is provenance-linked to its input artifact hashes.

## Phase 4 — API productization
- [ ] Stable versioned API surface.
- [ ] Authentication/session boundary.
- [ ] Authorization policy matrix.
- [ ] Request validation and size limits.
- [ ] Rate limiting and abuse controls.
- [ ] Pagination/filter/sort contracts.
- [x] Idempotent research-run mutation semantics with atomic job/idempotency transaction.
- [ ] Structured error model.

## Phase 5 — Data and artifact storage
- [ ] Tenant-scoped object storage abstraction.
- [ ] Content-addressed artifacts.
- [ ] Upload/download authorization.
- [ ] Retention and deletion policy.
- [ ] Dataset version registry.
- [ ] Reproducibility manifest generation.

## Phase 6 — Research services
- [ ] Governed analysis execution contract.
- [ ] Probability/edge service registry.
- [ ] Calibration and uncertainty outputs.
- [ ] Multiple-testing controls.
- [ ] OOS/replication state tracking.
- [ ] Economic cost/slippage context.
- [ ] Deterministic research artifact manifests.

## Phase 7 — Product UI
- [ ] Tenant/workspace shell.
- [ ] Claim creation and plan-lock workflow.
- [ ] Experiment/run/result explorer.
- [ ] Evidence lineage graph view.
- [ ] Validation/finding/replication status views.
- [ ] Research report export.
- [ ] Audit trail UI.

## Phase 8 — Billing and commercial controls
- [ ] Plan/entitlement model.
- [ ] Usage metering.
- [ ] Billing provider adapter.
- [ ] Subscription lifecycle handling.
- [ ] Grace-period and failed-payment states.
- [ ] Entitlement enforcement independent of UI.

## Phase 9 — Observability and security
- [ ] Structured application logs.
- [ ] Metrics/traces for API and jobs.
- [ ] Audit events for security-sensitive actions.
- [ ] Secret/config validation.
- [ ] Dependency and container scanning.
- [ ] Threat-model review.
- [ ] Tenant isolation red-team tests.

## Phase 10 — Production / disaster recovery
- [ ] Production deployment topology.
- [ ] Database backup and restore test.
- [ ] Object-storage recovery test.
- [ ] Queue/job recovery test.
- [ ] Migration rollback strategy.
- [ ] RPO/RTO documented and tested.
- [ ] Operational runbooks.

## Final launch gate
A release is **NOT production-ready** unless all applicable gates are green:

1. Research invariants pass.
2. Unit/integration/security tests pass.
3. Tenant isolation is verified.
4. Evidence lineage integrity is verified.
5. Idempotency and durable jobs are verified.
6. Backup/restore is verified.
7. Observability is live.
8. CI status is observed for the exact release commit.
9. No known high-severity security or data-integrity defect remains open.
10. The release artifact is reproducible and versioned.
