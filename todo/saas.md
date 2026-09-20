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
- [x] Connect graph projection to Experiment/Run/Result/Validation/Finding traversal APIs.
- [x] Add first-class contradiction/replication edges without mutating historical artifacts.
- [x] Add graph integrity and orphan detection gate.

## Phase 2 — Tenant-safe persistence
- [ ] Make workspace/tenant identity mandatory at every SaaS boundary.
  - [x] Reject ambiguous multi-workspace auth resolution; support explicit `X-Workspace-ID` selection.
- [ ] Implement canonical Supabase persistence adapters.
  - [x] Add tenant-scoped durable Supabase Research Claim adapter (persistence only; API exposure remains gated).
  - [x] Add tenant-scoped Research Claim customer API with fail-closed persistence and cross-workspace tests.
- [x] Enforce RLS for every tenant-owned table.
- [x] Add tenant-isolation integration tests.
  - [x] Golden Path result/evidence API cross-workspace isolation contract tests.
  - [x] Research Claim API cross-workspace lookup and pagination isolation coverage (API contract tests).
  - [x] Adversarial DB tenant-isolation suite covering cross-workspace reads/writes/deletes, workspace rebinding, child-parent mismatch, and privileged RPC boundaries (PR #129; exact-head CI + Supabase Database Security Tests green).
- [x] Add repository migration integrity gate (target-environment compatibility still release-gated).
  - [x] Production migration history independently verified against the repository's canonical migration sequence through `202609200009`.
  - [x] Required durable production objects and RLS verified in the target Supabase environment.
  - [x] Observed production migration drift resolved through the canonical migration workflow; `research_claim` and `audit_event` are present in production.

## Phase 3 — Durable execution
- [x] Introduce idempotency keys for research-run mutation with atomic durable reservation.
- [x] Add durable job records and state transitions.
- [x] Add retry policy with bounded attempts and explicit terminal states.
- [x] Add worker heartbeat/lease semantics.
- [x] Ensure every job output is provenance-linked to its input artifact hashes.

## Phase 4 — API productization
- [x] Stable versioned API surface.
- [ ] Authentication/session boundary.
  - [x] Research Claim endpoints consume the authenticated TenantContext and never trust workspace/creator request fields.
- [x] Authorization policy matrix.
- [x] Request validation and size limits.
- [x] Rate limiting and abuse controls.
- [x] Pagination/filter/sort contracts.
- [x] Idempotent research-run mutation semantics with atomic job/idempotency transaction.
- [x] Structured error model.

## Phase 5 — Data and artifact storage
- [x] Tenant-scoped object storage abstraction.
- [x] Content-addressed artifacts.
- [x] Upload/download authorization.
- [ ] Retention and deletion policy.
  - [x] Deterministic fail-closed retention eligibility contract.
  - [ ] Destructive retention executor with dependency resolution, audit events, and recovery/runbook coverage.
- [x] Dataset version registry.
- [x] Reproducibility manifest generation.

## Phase 6 — Research services
- [x] Add deterministic computational path planner v1 (method contracts, capability registry, prerequisite gates, immutable plan hash).
- [x] Governed analysis execution contract (immutable AnalysisResult bound to planner output).
- [x] Probability/edge service registry.
- [x] Calibration and uncertainty outputs.
- [x] Bind calibration sample evidence to governed edge eligibility.
- [x] Add deterministic Holm/Benjamini-Hochberg multiple-testing correction primitives.
- [x] Enforce multiple-testing results at governed edge eligibility.
- [x] OOS/replication state tracking.
- [x] Economic cost/slippage context.
- [x] Bind economic cost/slippage context to governed edge eligibility.
- [x] Deterministic research artifact manifests.

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
- [x] Tenant isolation red-team tests.

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

- Evidence governance v1: immutable OOS/replication artifact contracts bound to governed edge eligibility (PR #76).

## Verification discipline

- Structured API errors and request-correlation metadata are implemented and covered by SaaS API tests.
- Production readiness remains gated on exact-release CI, integration, security, tenant-isolation, target-environment schema parity, and operational verification.
- 2026-09-20 production migration drift was repaired through the canonical migration workflow; the target now contains `public.research_claim`, `public.audit_event`, and the required QROS tenant/server tables with RLS enabled.
- The target Supabase Security Advisor still reports nine unrelated legacy public tables with RLS disabled. These are not QROS tenant tables and remain a separate security remediation item; enabling RLS blindly would risk breaking their existing access model.

## Golden Path V1 — active milestone
- [x] Freeze QROS SaaS architecture and product workflow boundary.
- [x] Publish product flow, API contract, production checklist, and batch execution roadmap.
- [x] Dataset upload/version API and durable storage boundary.
- [x] Research Run API, durable idempotency, queue and worker lease/result provenance.
- [x] Research Claim durable persistence and customer API.
- [x] Tenant-scoped Result read API.
- [x] Tenant-scoped Evidence read API.
- [ ] Auth provider production integration.
- [ ] End-to-end staging Golden Path execution.
- [ ] Production Golden Path execution.
