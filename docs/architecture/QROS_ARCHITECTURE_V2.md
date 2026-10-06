# QROS Architecture v2 — Minimal Cost / Maximum Speed

Status: ACTIVE REFACTOR BASELINE
Branch: main
Base: 750aa71370287b7c1defd5c1abb653ef185b9f6c

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
The former `researchos.research_execution.py` boundary has been migrated into `researchos.research_core.provenance` and the obsolete module has been deleted after caller migration and reference verification.

`researchos.pipeline`, `researchos.decision_engine`, `researchos.objects`, and `researchos.repository` are not deletion targets merely because they are old. Each is a live bounded context until an exact canonical replacement is proven.

### Legacy boundary classification — 2026-10-06

The current reference audit establishes the following:

- `researchos.pipeline` is a live 11-stage research-object lifecycle coordinator. It is used by local interfaces, agent tools, and dedicated pipeline verification tests. Its semantics are object creation, reference validation, parent-link maintenance, persistence, and audit recording. `research_core.runner` is **not** a drop-in replacement: it executes the frozen scientific workflow and exposes a different contract.
- `researchos.objects` is the object graph consumed by the pipeline, storage, attribution, macro, memory, and tests. It is a coherent bounded model, not a proven duplicate of `research_core.contracts`.
- `researchos.repository` is the repository contract used by that object graph and by multiple domain modules. It is distinct from `researchos.storage.repository` and `researchos.data_engine.repository`; name similarity is not sufficient evidence for consolidation.
- `researchos.decision_engine` remains a separate decision bounded context until its contracts and callers are proven equivalent to a canonical component.

Therefore this block makes **no speculative deletion**. The next cleanup block must target one concrete boundary only after a caller-by-caller semantic mapping proves a replacement. This is the required constraint-first rule: reduce duplication only where equivalence is demonstrated, not where names merely overlap.

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
- `researchos.research_core.provenance` — canonical provenance-bound execution boundary.
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