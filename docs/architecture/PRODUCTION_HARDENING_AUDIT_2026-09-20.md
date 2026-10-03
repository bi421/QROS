# Production Hardening Architecture Audit — 2026-09-20

Status: **AUDIT COMPLETE / IMPLEMENTATION PENDING**
Scope: architecture, source-of-truth, SaaS production readiness.
Explicit exclusion: **retention/reconciliation files, migrations, and tests were not modified.**

## 1. Main / CI evidence

Audited release baseline:

- Branch: `main`
- HEAD: `c7faafd6c6116549d93c014876227f8367c282ae`
- HEAD message: `fix(retention): enforce governed reconciliation transitions (#122)`
- CI run #1525 for this exact SHA: success.
- Supabase Database Security Tests #34 for this exact SHA: success.
- Main branch is not protected and currently has no required status checks configured.

This is CI evidence for the exact commit, not evidence of production readiness.

## 2. Current open PR ownership

The active retention PR is #123 `feat/retention-reconciliation-recovery-v1`.

This production-hardening work intentionally uses a separate branch and does not modify retention/reconciliation surfaces.

Other open PRs include historical audit/research work (#6, #14, #61, #65, #66, #67). They are not assumed merged or complete without exact CI/merge evidence.

## 3. Canonical engine/source-of-truth audit

The repository explicitly declares:

- `researchos/quant_engine/` = canonical Python research/quant API.
- `researchos/engines/quant/` = native C++/nanobind implementation backend.
- `researchos/data_engine/` = canonical Python data-engine API.
- `researchos/engines/data/` = historical duplicate; no new features.

The repository still contains substantial Python implementation under `researchos/engines/quant/`, including public-looking modules such as `backtest.py`, `backend.py`, `execution.py`, `indicators.py`, `metrics.py`, `router.py`, `statistics.py`, `strategy.py`, and model/probability/validation subpackages.

This is **not sufficient evidence to delete or migrate them**. The canonical ownership document explicitly says it does not prove historical implementations have been removed.

Adversarial source search also found non-native consumers importing `researchos.engines.quant`, including:

- `researchos/signals/multi_feature.py`
- `researchos/macro/gold_factor_model/comparison.py`
- `researchos/tests/test_quant_backtest_metrics.py`

Therefore the source-of-truth boundary is documented but not yet fully enforced across the repository.

### Decision

Do **not** perform a broad engine migration in this PR.

Next isolated hardening step should be a consumer-by-consumer dependency migration with parity tests. Deletion/rename must remain a separate PR.

## 4. SaaS production boundary

The repository already defines the intended production boundary:

`Auth -> Workspace -> Dataset -> DatasetVersion -> ResearchRun -> Analysis -> Evidence -> Claim -> Result`

Production composition uses Supabase-backed persistence, durable jobs, tenant authorization, and request correlation.

The production-readiness contract explicitly lists these as still environment-dependent:

1. target-environment migration/schema compatibility;
2. real JWT authentication;
3. target-database tenant isolation;
4. durable dataset storage;
5. queue/worker execution;
6. claim/evidence persistence;
7. real billing webhook;
8. backup/restore;
9. queue/job recovery;
10. exact-release production smoke test.

These cannot be truthfully marked complete from repository CI alone.

## 5. Observability gap

Repository contracts require request correlation and operational monitoring, but the production checklist still has:

- monitoring/alerting: pending;
- p95 latency measurement: pending;
- API error-rate measurement: pending;
- SLOs/on-call: pending.

Therefore the next implementation should establish a minimal production observability contract before launch:

- correlation ID propagation;
- structured request/job lifecycle events;
- health/readiness distinction;
- latency/error counters;
- worker lease/recovery signals;
- secret-safe logging rules.

No production credentials or real user data are required for the repository-side contract work.

## 6. Backup / disaster-recovery gap

The launch checklist explicitly leaves backup/restore, RPO/RTO, queue recovery, and object-storage recovery pending.

Repository-only work can define and test:

- backup ownership;
- restore verification procedure;
- migration compatibility checks;
- queue recovery invariants;
- artifact/object-storage recovery expectations;
- RPO/RTO evidence format.

An actual restore drill requires the target environment and must not be represented as complete until observed.

## 7. Staging Golden Path gap

The repository Golden Path is substantially implemented at the API/persistence-contract level, but the production-readiness document explicitly says staging end-to-end execution remains unverified.

The required evidence is an actual staging execution of:

`Authenticate -> Workspace -> Dataset -> DatasetVersion -> ResearchRun -> Analysis -> Evidence -> Claim -> Result`

including tenant isolation and durable persistence.

Repository tests alone are insufficient for this gate.

## 8. Roadmap synchronization

`todo/saas.md` correctly keeps the environment-dependent gates unchecked.

No new `[x]` was justified by this audit.

In particular, the following remain unchecked and should stay that way until real evidence exists:

- Auth provider production integration;
- staging Golden Path;
- production Golden Path;
- destructive retention executor/recovery;
- observability/security operational gates;
- backup/restore and disaster recovery.

## 9. Production launch conclusion

Current evidence supports:

- exact main SHA CI success;
- exact main SHA Supabase security-test success;
- documented SaaS architecture boundary;
- durable production composition in repository;
- explicit production blockers.

Current evidence does **not** support:

- production-ready status;
- completed staging Golden Path;
- completed backup/restore;
- completed disaster recovery;
- completed observability;
- fully resolved duplicate/source-of-truth migration.

The next non-retention implementation unit is therefore **observability contract hardening**, followed by repository-side DR/restore readiness, then staging Golden Path verification when a real staging environment is available.
