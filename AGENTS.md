# QROS AGENTS.md

## 0. Purpose

This file is the operating contract for all future QROS engineering, hardening,
validation, release-readiness, and production-readiness work.

Repository: bi421/QROS

Baseline main SHA at creation:
4d9cc08825a241a03545ff521c667e4ccd733c9a

This document is a roadmap and verification protocol. It is not evidence that
future phases have already been executed.

---

## 1. Non-negotiable engineering rules

### 1.1 Exact-SHA discipline

Every substantive change MUST:

1. start from the exact current main SHA;
2. use a dedicated branch;
3. keep the diff narrow and auditable;
4. add focused regression coverage when behavior or a contract changes;
5. run local validation appropriate to the changed surface;
6. open a PR;
7. verify CI against the exact PR head SHA;
8. merge only after required gates are GREEN;
9. verify the resulting main SHA;
10. verify post-merge gates against that exact resulting SHA.

Never infer a result from a nearby commit.

If main changes while work is in progress, stop and reconcile the new base before
changing code.

### 1.2 No artificial green

Never use or introduce:

- || true to hide required failures;
- --exit-zero for required checks;
- continue-on-error: true for required gates;
- broad exception swallowing that converts a required failure into success;
- skipped required validation merely to obtain a green CI result;
- empty commits;
- formatter-only noise unless formatter compliance is itself the intended change.

### 1.3 Facts versus claims

Always distinguish:

- FACT: directly observed from code, CI, GitHub configuration, or an executed environment;
- INFERENCE: reasoned interpretation;
- NOT VERIFIED: required evidence is not currently available;
- BLOCKER: concrete failure preventing the phase from being accepted.

Passing repository tests does NOT prove production readiness.

Passing CI does NOT prove institutional-grade operation.

Documentation does NOT substitute for execution evidence.

### 1.4 Secrets

Never commit, print, paste, or expose secret values.

It is acceptable to verify secret names/existence only when the interface exposes
that metadata safely.

Local .env and generated credential files remain untracked and must not be staged
unless explicitly intended and demonstrably non-secret.

---

## 2. Current verified baseline

At creation of this file:

- Main SHA: 4d9cc08825a241a03545ff521c667e4ccd733c9a.
- Production DB backup workflow uses environment: production.
- Production schema-parity workflow uses environment: production.
- Exact release verification is tag-triggered on v* and is read-only.
- Release-readiness governance rejects known fail-open workflow patterns.
- Production Environment Required Reviewers: ENABLED.
- Production Environment Wait Timer: DISABLED.
- Production Environment Deployment Branches/Tags: No restriction.
- The exact GitHub Environment administration API was not available through
  the connected integration during the preceding audit; UI verification is
  authoritative for those hosted settings.
- Production secret values were not exposed.

Known release/production evidence boundaries:

- Repository-side executable gates exist.
- Target-environment execution remains a separate evidence requirement.
- RPO/RTO remain unverified until measured by an actual drill.
- Production launch remains blocked until the target environment demonstrates
  the documented recovery, schema, authentication, isolation, storage, job,
  release, and smoke-test evidence.

---

# 3. Phase roadmap

The phases below are ordered. Do not skip ahead merely because later work is
interesting.

A phase is complete only when its acceptance criteria and evidence requirements
are satisfied.

---

## PHASE 0 — Governance and baseline integrity

### Objective

Keep the repository's control plane deterministic before adding more features.

### Work

0.1 Maintain the exact-SHA workflow.

0.2 Audit governed workflows for:
- unsafe triggers;
- excessive permissions;
- fail-open patterns;
- accidental production access;
- unreviewed environment usage;
- secret exposure.

0.3 Keep the release-readiness static audit synchronized with all governed
production/staging/release controls.

0.4 Periodically verify GitHub-hosted controls separately from repository YAML:
- production Environment protection;
- branch/ruleset protection;
- required status checks;
- deployment restrictions.

### Verification

Local:

~~~text
cd C:\Users\User\Desktop\QROS
git rev-parse HEAD
git status --short
git diff --check
python ops/release/readiness_audit.py
ruff check .
mypy
python -m compileall researchos
~~~

GitHub evidence:
- CI GREEN at exact SHA.
- Release Readiness Static Gate GREEN at exact SHA.
- Supabase Database Security Tests GREEN at exact SHA when applicable.

Acceptance:
- No unexplained fail-open path.
- No unverified claim presented as a fact.
- No new production privilege without an explicit control.

---

## PHASE 1 — Repository architecture and source-of-truth integrity

### Objective

Prevent duplicate implementations, ambiguous import paths, dead migration
layers, and hidden build artifacts from reappearing.

### Work

1.1 Inventory Python packages, C++/native modules, engine directories, data
engine directories, build trees, generated files, and root-level executable
scripts.

1.2 Detect duplicate or overlapping implementations.

1.3 Define and document the canonical source path for each major subsystem.

1.4 Remove obsolete duplicates only when import/reference/search evidence proves
they are unused.

1.5 Keep generated/build output outside governed source paths or explicitly
excluded.

### Verification

Before changes:
- repository-wide path inventory;
- import/reference search;
- test coverage/reference search for candidate files.

After changes:

~~~text
git diff --check
ruff check .
mypy
python -m compileall researchos
pytest -q
~~~

Then:
- compare import/reference counts;
- confirm canonical path is the only active implementation;
- run exact-head CI;
- inspect changed-file list for unintended deletions.

Acceptance:
- no ambiguous duplicate active implementation remains;
- no import path is broken;
- no hidden build tree is treated as source.

---

## PHASE 2 — Static typing closure

### Objective

Reduce and then close meaningful mypy debt in governed production source
without hiding errors.

### Work

2.1 Establish an authoritative mypy scope.

2.2 Fix production contract clusters in small batches.

2.3 Prefer type-correct domain models and adapters over blanket ignores.

2.4 Use explicit narrowing, typed protocols, correct numeric/container types,
and well-defined return values.

2.5 Treat third-party untyped imports separately from real application typing
defects.

2.6 Any type: ignore must be narrow, justified, and reviewed.

### Verification

For each batch:

~~~text
mypy
pytest -q
ruff check .
python -m compileall researchos
git diff --check
~~~

Track:
- total error count;
- error count by code;
- files affected;
- newly introduced ignores;
- regression-test result.

Acceptance:
- CI mypy uses the intended Python/runtime target;
- no required mypy gate is bypassed;
- error reductions are attributable to real fixes;
- new errors do not regress the established baseline.

Do not claim "mypy complete" until the governed CI scope is actually clean.

---

## PHASE 3 — Property-based and invariant testing

### Objective

Test contracts that example-based tests cannot adequately cover.

### Work

3.1 Identify pure/domain-heavy invariants:
- dataset versioning;
- canonicalization/hashing;
- tenant boundaries;
- evidence/result serialization;
- planner/claim binding;
- probability/calibration contracts;
- pagination/filtering;
- idempotency;
- numeric edge cases.

3.2 Add Hypothesis strategies with bounded, deterministic inputs.

3.3 Test:
- round-trip properties;
- idempotence;
- monotonicity where contractually required;
- no cross-tenant leakage;
- hash stability;
- serialization/deserialization consistency;
- invalid-input rejection.

3.4 Keep property tests independent of live production data.

### Verification

~~~text
pytest -q tests
pytest -q tests -k "hypothesis or property"
ruff check .
mypy
git diff --check
~~~

For important invariants:
- reproduce at least one failure deterministically when a bug is found;
- preserve the regression test;
- document assumptions and bounds.

Acceptance:
- each new property test proves a stated invariant;
- no flaky randomness;
- no production secrets/data required;
- CI executes the intended property tests.

---

## PHASE 4 — Production observability and failure diagnosis

### Objective

Make failures observable, attributable, and diagnosable without leaking
sensitive data.

### Work

4.1 Establish request/job correlation identifiers.

4.2 Standardize structured logs around:
- request;
- tenant/workspace;
- research run/job;
- dataset/version;
- result/finding;
- failure class.

4.3 Add metrics for:
- request rate;
- error rate;
- latency;
- queue depth;
- job success/failure/retry;
- time-to-first-valid-research-result;
- storage operation failures.

4.4 Add health/readiness semantics:
- liveness;
- readiness;
- dependency health.

4.5 Define log redaction rules for credentials, tokens, private payloads, and
tenant-sensitive content.

### Verification

Code:

~~~text
pytest -q
ruff check .
mypy
python -m compileall researchos
~~~

Staging:
- execute the relevant golden-path and failure-path workflows;
- confirm correlation IDs connect API request -> job -> result -> evidence;
- confirm sensitive values are absent from logs;
- measure latency/error metrics.

Acceptance:
- failures can be traced to a correlation chain;
- sensitive data is not emitted;
- health/readiness endpoints reflect actual dependency state.

---

## PHASE 5 — Staging Golden Path execution

### Objective

Convert repository-side claims into observed end-to-end staging evidence.

### Work

5.1 Run the staging golden path against the intended staging environment.

5.2 Verify:
- health/readiness;
- authenticated tenant identity;
- immutable dataset;
- tenant isolation;
- governed claim/plan lock;
- research-run enqueue;
- worker completion;
- result integrity/provenance;
- evidence visibility;
- claim binding;
- finding/report creation;
- time-to-first-valid-research-result.

5.3 Save workflow artifacts/evidence for each execution.

### Verification

Use the manual staging workflows, with the staging Environment and its
required controls.

Required evidence:
- successful workflow run URL/ID;
- exact commit SHA;
- uploaded evidence artifact;
- tenant-isolation assertions;
- result/evidence integrity checks;
- timing measurements.

Acceptance:
- the same exact release candidate passes the full golden path;
- no cross-tenant access is observed;
- persisted result/evidence contracts match the repository model.

Repository tests alone do not close this phase.

---

## PHASE 6 — Staging performance and reliability

### Objective

Demonstrate measurable latency/error behavior rather than relying on code
inspection.

### Work

6.1 Run the staging performance gate.

6.2 Establish workload assumptions.

6.3 Measure:
- p95 latency;
- maximum error rate;
- queue/job completion;
- retry/recovery behavior;
- time-to-first-valid-research-result.

6.4 Record environment, workload, dataset size, and commit SHA with each run.

### Verification

Required evidence:
- exact SHA;
- performance workflow result;
- p95 result;
- error-rate result;
- workload parameters;
- any failed/retried job evidence.

Acceptance:
- declared thresholds are satisfied for the documented workload;
- failures are reproducible or explained;
- no performance claim is generalized beyond the tested workload.

---

## PHASE 7 — Backup, restore, and disaster-recovery drills

### Objective

Prove recovery behavior through actual execution.

### Work

7.1 Database backup/restore:
- create backup;
- restore into an isolated target;
- verify migrations;
- verify schema integrity;
- verify key application contracts.

7.2 Object-storage recovery:
- create deterministic artifact;
- record SHA-256;
- export independent recovery copy;
- restore;
- re-upload;
- download;
- byte-compare.

7.3 Job/recovery exercise:
- force or simulate a controlled interruption;
- verify idempotency/retry semantics;
- confirm result persistence after recovery.

7.4 Measure RPO/RTO.

### Verification

For every drill:
- exact source SHA;
- environment;
- start/end timestamps;
- backup artifact identity;
- integrity/hash evidence;
- restore result;
- application/schema verification;
- measured RPO;
- measured RTO.

Acceptance:
- recovery path actually executes;
- integrity checks pass;
- no destructive production experiment is performed without approved scope;
- RPO/RTO are reported as measured values, not documentation claims.

---

## PHASE 8 — Production schema, security, and tenant-boundary verification

### Objective

Verify the exact target production environment without destructive changes.

### Work

8.1 Run production schema parity.

8.2 Verify:
- migration history;
- schema compatibility;
- RLS policy presence and behavior;
- tenant isolation;
- required indexes/constraints;
- application-to-database contract alignment.

8.3 Run Supabase database security checks.

8.4 Inspect relevant Auth hardening findings separately from repository code.

### Verification

Production operations must use:
- the production Environment;
- required reviewer approval;
- the intended workflow;
- exact release SHA.

Required evidence:
- schema-parity run;
- security-test run;
- tenant-isolation evidence;
- no unauthorized schema mutation;
- any external platform warnings documented separately.

Acceptance:
- target production schema matches the version-controlled contract;
- security tests pass;
- unresolved external platform warnings are explicitly tracked.

---

## PHASE 9 — Production storage, jobs, claims, and evidence execution

### Objective

Verify that durable SaaS workflows work in the real target environment.

### Work

9.1 Upload/version/download a controlled dataset.

9.2 Verify immutable version semantics and hash stability.

9.3 Enqueue and complete a controlled research run.

9.4 Verify persisted result integrity/provenance.

9.5 Verify claim/evidence persistence and tenant isolation.

9.6 Verify recovery/retry behavior where applicable.

### Verification

Record:
- exact release SHA;
- dataset/version identifiers;
- hashes;
- job lifecycle evidence;
- result/evidence IDs;
- tenant-boundary checks;
- logs/correlation IDs.

Acceptance:
- end-to-end persisted workflow succeeds in the target environment;
- no cross-tenant data is visible;
- artifacts are independently verifiable.

---

## PHASE 10 — Billing and external-provider integration

### Objective

Verify integrations that repository tests cannot prove alone.

### Work

10.1 Test billing webhook behavior with the real intended provider/test mode.

10.2 Verify:
- signature validation;
- replay/idempotency protection;
- customer/tenant mapping;
- failure handling;
- persistence.

10.3 Record provider-side evidence without exposing credentials.

### Verification

Required:
- provider event ID;
- exact application SHA;
- webhook response;
- persisted state;
- retry/idempotency result.

Acceptance:
- valid events are accepted;
- invalid/forged events are rejected;
- duplicate delivery does not create duplicate business effects.

---

## PHASE 11 — Exact release verification

### Objective

Prove that a release tag corresponds exactly to the commit that passed release
gates.

### Work

11.1 Create a release candidate only after all prerequisite phases have passed.

11.2 Verify:
- migrations;
- ruff;
- mypy;
- tests against the intended target;
- backup verification;
- exact health evidence;
- required artifacts.

11.3 Ensure release workflow is triggered only from the intended release tag.

### Verification

Required:
- release tag;
- exact commit SHA;
- Exact Release Verification workflow GREEN;
- migration evidence;
- backup/restore evidence;
- health evidence artifact;
- all required CI gates GREEN.

Acceptance:
- tag resolves to the exact verified commit;
- no gate was bypassed;
- artifacts are bound to the exact SHA.

---

## PHASE 12 — Production launch evidence review

### Objective

Make the final readiness decision from evidence, not optimism.

### Review checklist

Confirm all relevant phases have:
- exact SHA evidence;
- environment evidence;
- successful workflow evidence;
- artifact evidence;
- measured operational metrics;
- tracked exceptions.

Review outstanding blockers:
- schema parity;
- authentication;
- tenant isolation;
- storage durability;
- job execution/recovery;
- claim/evidence persistence;
- billing webhook;
- backup/restore;
- queue/job recovery;
- production smoke;
- RPO/RTO.

### Acceptance

Do not label QROS "production-ready" until the documented production-readiness
gates have been executed in the intended target environment and all required
blockers are closed or explicitly accepted by the responsible operator.

---

# 4. Standard change protocol

For any future code/configuration change:

### Step A — Establish base

~~~text
cd C:\Users\User\Desktop\QROS
git fetch origin
git checkout main
git pull --ff-only origin main
$BASE = git rev-parse HEAD
$BASE
~~~

The reported SHA is the only valid base for the change.

### Step B — Create branch

~~~text
git checkout -b <type>/<short-purpose>
~~~

### Step C — Inspect before editing

Record:
- relevant files;
- current behavior;
- existing tests;
- applicable CI gates;
- security/tenant implications;
- whether the issue is code, configuration, or external environment.

### Step D — Make the smallest auditable change

Do not refactor unrelated code.

### Step E — Local validation

Minimum default:

~~~text
git diff --check
ruff check .
mypy
python -m compileall researchos
pytest -q
python ops/release/readiness_audit.py
~~~

Add targeted tests/commands for the changed subsystem.

### Step F — Commit

Use a factual commit message describing the change.

Never create an empty commit.

### Step G — PR

PR body must state:
- problem;
- root cause;
- exact change;
- tests;
- risks;
- evidence;
- known NOT VERIFIED items.

### Step H — Exact-head CI

Before merge, verify the workflows are attached to the exact PR head SHA.

At minimum, where applicable:
- CI;
- Release Readiness Static Gate;
- Supabase Database Security Tests.

### Step I — Merge

Merge only after required gates are GREEN and no unexplained failure remains.

### Step J — Post-merge verification

Immediately verify:

~~~text
refs/heads/main == expected merge/main SHA
~~~

Then verify post-merge required gates against that exact SHA.

---

# 5. Environment/configuration protocol

Repository YAML and GitHub-hosted controls are different evidence classes.

### Repository-side

Can be verified from source:
- environment: production;
- workflow triggers;
- permissions;
- secret references;
- fail-open patterns;
- required scripts and markers.

### GitHub-hosted

Must be verified from GitHub configuration/UI:
- Environment existence;
- required reviewers;
- wait timer;
- deployment branch/tag restrictions;
- environment protection rules;
- environment secret metadata.

Never add source-code markers to pretend a GitHub-hosted setting exists.

Current production Environment evidence:
- Required reviewers: ENABLED.
- Wait timer: DISABLED.
- Deployment branches/tags: No restriction.

Do not silently change these settings as part of a code PR.

---

# 6. Definition of done

A task is DONE only when all applicable items are true:

- [ ] Scope is explicit.
- [ ] Root cause is identified or uncertainty is documented.
- [ ] Change is minimal.
- [ ] Regression coverage exists where behavior changed.
- [ ] Local checks pass.
- [ ] No secret values were exposed.
- [ ] No fail-open behavior was introduced.
- [ ] PR exists when repository history should change.
- [ ] Exact-head CI is GREEN.
- [ ] Post-merge main SHA is verified.
- [ ] Post-merge required gates are GREEN.
- [ ] Environment execution evidence exists when the task depends on a real
      environment.
- [ ] Operational claims are limited to the population/environment actually
      tested.

---

# 7. Evidence record template

For every completed phase, record:

~~~text
PHASE:
DATE:
REPOSITORY:
BASE SHA:
FINAL SHA:
ENVIRONMENT:
WORKFLOW / RUN:
RESULT:
ARTIFACTS:
LOCAL TESTS:
SECURITY / ISOLATION RESULT:
METRICS:
NOT VERIFIED:
BLOCKERS:
DECISION:
~~~

For GitHub Actions, always retain:
- workflow name;
- run number/ID;
- exact head SHA;
- result;
- relevant artifact names.

---

# 8. Stop conditions

Stop the current change instead of guessing when:

- main changed unexpectedly;
- required environment configuration is not observable;
- secret scope is ambiguous;
- a required gate fails;
- a test failure cannot be attributed;
- a migration would be destructive or unsafe;
- tenant isolation evidence is inconclusive;
- production behavior is inferred only from local tests;
- a proposed fix would bypass or weaken an existing gate.

When stopped, report:
- FACT;
- GAP/BLOCKER;
- NOT VERIFIED;
- safest next action.

Do not create a PR merely to record uncertainty.

---

# 9. Priority order for future work

Unless a new concrete blocker changes the order, follow:

1. Governance/baseline integrity.
2. Architecture/source-of-truth integrity.
3. Static typing closure.
4. Property-based contract testing.
5. Observability.
6. Staging Golden Path execution.
7. Staging performance/reliability.
8. Backup/restore and disaster-recovery drills.
9. Production schema/security/tenant verification.
10. Production storage/jobs/claims/evidence execution.
11. Billing/provider integration verification.
12. Exact release verification.
13. Final production-readiness evidence review.

A later phase must not be used to conceal an earlier unresolved blocker.

---

# 10. Final operating principle

QROS advances from:

CODE
-> LOCAL TESTS
-> CI
-> STAGING EVIDENCE
-> PRODUCTION EVIDENCE
-> MEASURED OPERATIONAL EVIDENCE

Each arrow requires proof.

Never replace missing evidence with confidence, documentation, or a green
nearby commit.


---

# 11. Parallel workstream protocol — 2026-09-27

The repository is now being advanced by two independent engineering workstreams.
Parallel work is allowed only when ownership and file scope are explicit.

## 11.1 Current exact baseline

Current main SHA after PR #367:
`03191c86cdff541ac07cfca4291e9801ffab64bc`

Phase 2 — Static typing:
- PR #367 merged with the governed typing scope at zero mypy errors.
- No production typing files required modification in that governed scope.
- This does NOT establish repo-wide mypy == 0.

Phase 3 — Property/invariant testing:
- PR #367 merged.
- `researchos/tests/test_quality_property_contracts.py` added 197 lines.
- 12 property/invariant tests execute in CI.
- Exact PR-head CI, Release Readiness, and Supabase gates passed.
- Post-merge main gates passed at the exact resulting SHA.

## 11.2 Workstream A — platform / production engineering

Workstream A owns:
- Phase 1 architecture/source-of-truth integrity;
- Phase 4 observability;
- Phase 7 backup/restore and disaster recovery;
- Phase 8 production schema/security/tenant-boundary verification;
- Phase 9 production storage/jobs/claims/evidence execution;
- Phase 10 billing/provider integration;
- Phase 11 exact release verification;
- Phase 12 evidence review.

Workstream A must not modify B-owned quantitative research logic merely to simplify
its own branch.

Current A branches/PRs must always disclose their exact base SHA.

## 11.3 Workstream B — quantitative research / validation engineering

Workstream B owns research/quantitative validation work only, including:
- XAUUSD walk-forward validation;
- out-of-sample holdout enforcement;
- DXY/US10Y/VIX feature validation;
- Bayesian probability/calibration contracts;
- quantitative result artifacts and research methodology documentation.

Workstream B must not modify:
- `.github/workflows/`;
- `AGENTS.md`;
- production/staging Environment controls;
- SaaS authentication/authorization/storage/billing runtime;
- observability/runtime operations;
- backup/recovery controls;
- canonical architecture/scope guards.

B-owned changes must remain evidence-driven and must not introduce trading
execution or broker-side actions.

## 11.4 Cross-workstream synchronization

Before any PR:
1. fetch and verify the exact current main SHA;
2. create a dedicated branch from that SHA;
3. inspect the other workstream's open PRs for file overlap;
4. do not edit the same files/contract surface concurrently;
5. if main changes, stop and reconcile before further code changes.

A workstream may merge only after its own exact-head required gates are GREEN.
A merge on another branch is not evidence for a different SHA.

## 11.5 Phase ownership does not transfer evidence

Passing CI for one workstream does not close another workstream's phase.
Real staging/production execution remains separate evidence even when repository
tests are green.

## 11.6 Required reporting

Every parallel-workstream update must state:
- current main SHA;
- branch and head SHA;
- files changed;
- exact CI/release/security evidence;
- NOT VERIFIED items;
- BLOCKER items, if any.

Never report a phase as complete merely because another workstream passed CI.
