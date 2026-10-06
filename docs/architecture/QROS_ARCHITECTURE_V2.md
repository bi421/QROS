# QROS Architecture v2 — Minimal Cost / Maximum Speed

Status: ACTIVE REFACTOR BASELINE
Branch: refactor/architecture-simplification-20261006
Base: eb3be146ec70b648db3eee2917c7164fca447f5b

## Objective
Optimize for the smallest implementation and validation cost that preserves scientific correctness, tenant isolation, provenance, fail-closed governance, and release safety.

Rule: change scope == validation scope. Full-system validation is a release property, not the default developer loop.

## Canonical architecture
Do not create another generic core package. The repository already has three canonical scientific components:

- `researchos.data_engine` — canonical market-data API.
- `researchos.quant_engine` — canonical Python quantitative/research API.
- `researchos.research_core` — application-independent scientific workflow, contracts, evidence and runner.

Delivery:
- `researchos.saas` — auth, workspace, entitlement, API, job orchestration and tenant delivery.
- `researchos.interfaces` — local CLI/API interfaces where still required.

Backend/infrastructure:
- `researchos.engines.quant` — native C++/nanobind implementation only.
- Supabase/storage/queue implementations at the delivery boundary.

## Canonical flow
Local: interface -> research_core -> quant/data engines -> result/evidence.
SaaS: API -> auth/workspace/entitlement -> job -> worker -> research_core -> backend -> evidence/result -> persistence.

## Dependency rules
Allowed: delivery -> domain; domain -> canonical domain components; quant_engine -> engines.quant adapter; delivery -> persistence/backend.
Forbidden: research_core/data_engine/quant_engine -> saas; scientific modules -> Supabase/FastAPI/billing/workspace; engines.quant -> Python domain API.

## Canonical object rule
One concept gets one authoritative representation: DatasetVersion, ResearchRequest/RunCommand, ResearchRun, ResearchResult, Evidence, Provenance. New wrapper/envelope/resolver types require a real semantic reason.

## Execution simplification
`researchos.research_execution.py` is currently live and must not be deleted blindly. It must either become the canonical execution boundary or be migrated into `research_core`, then removed after all references disappear.

`researchos.pipeline`, `researchos.decision_engine`, and older object/repository systems are legacy candidates only where current runtime/test references no longer exist.

## Phase 5.2
Prepare immutable input once: raw input -> PreparedResearchData -> feature-set evaluations. Do not rebuild identical source transformations for every feature set.

## Validation levels
L0 changed test: `python -m pytest <changed_test> -q`
L1 affected subsystem: `python -m pytest <affected_test_root> -q`
L2 PR: affected validation + mandatory integrity/security/integration checks
L3 release: complete scientific + SaaS + migration + type + security + supply-chain validation

L0/L1 must not invoke Supabase, production stores, billing, or unrelated subsystems.

## Import rule
Package `__init__.py` files are lightweight namespaces. Production clients, queues, stores and FastAPI apps are created only by explicit runtime entrypoints.

## Deletion rule
1. prove canonical replacement; 2. enumerate references; 3. migrate callers; 4. run L0/L1; 5. delete obsolete tests; 6. delete legacy module; 7. import smoke test; 8. L2.

No speculative mass deletion.

## Current known non-deletion candidates
- `researchos.research_execution.py` — live references.
- `researchos.pipeline` — live callers/tests.
- `researchos.decision_engine` — live callers/tests.
- `researchos.objects` / `researchos.repository` — live callers/tests.

Established canonical duplicate policy: `researchos.data_engine` is canonical; `researchos.engines.data` is obsolete and must not receive new code.

## Success criteria
- small domain changes do not import SaaS infrastructure;
- targeted tests run in seconds where practical;
- Phase 5.2 preparation is shared;
- local validation scopes are explicit;
- release gates retain full safety strength;
- every deletion has a reference audit trail;
- competing abstractions decrease after each refactor block.