# QROS Architecture v2 — Minimal-Cost / Maximum-Speed Design

Status: PROPOSED IMPLEMENTATION BASELINE
Branch: refactor/architecture-simplification-20261006
Base: eb3be146ec70b648db3eee2917c7164fca447f5b

## Objective
Reduce developer feedback time and runtime coupling without weakening scientific integrity, tenant isolation, provenance, fail-closed governance, or production release gates.

Primary optimization target:
    smallest change -> smallest validation scope -> fast feedback

Production target:
    full release gate remains authoritative.

## Canonical layers
QROS v2 has four architectural layers.

### 1. Core
researchos/core/
Owns only deterministic research semantics: input/domain types, dataset/version semantics, experiment execution, evaluation, evidence, provenance, scientific invariants.
Core MUST NOT import FastAPI, Supabase, billing, workspace/auth, queue implementations, browser/UI, or deployment secrets.

### 2. Runtime
researchos/runtime/
Owns execution mechanics: run request, worker, queue boundary, lease/heartbeat/fencing, runner invocation, result persistence boundary.
Runtime depends on Core. Core does not depend on Runtime.

### 3. SaaS
researchos/saas/
Owns delivery concerns: auth, workspace/membership, entitlement/billing, API, tenant persistence, dataset upload orchestration.
SaaS calls Runtime/Core through narrow boundaries.

### 4. Adapters
researchos/adapters/
Owns external implementations: Supabase, storage, queue, external market/data sources, C++/nanobind bridge where applicable.
Adapters depend inward. Domain code does not depend on concrete adapters.

## Canonical execution path
SaaS/API -> authorization -> RunCommand -> Runtime -> Core -> Evidence/Result -> persistence adapter
Local mode: CLI -> RunCommand -> Runtime -> Core -> Result
The same scientific Core is used in both modes.

## Dependency rule
Allowed direction: adapters -> saas/runtime -> core
Not allowed: core -> saas; core -> adapters; core -> FastAPI/Supabase; runtime -> billing; scientific code -> tenant/auth state.

## Canonical objects
Keep one authoritative representation for each concept: DatasetVersion, RunCommand, ResearchRun, ResearchResult, Evidence, Provenance.
Do not create wrapper/envelope/adapter types unless they carry genuinely different semantics.

## Validation architecture
L0 — changed test: python -m pytest <changed_test> -q
L1 — affected subsystem: targeted package tests only.
L2 — PR gate: changed-scope checks plus required integration/security checks.
L3 — release: full test, type, security, provenance, migration, supply-chain and production verification.
A local code change MUST NOT require L3 validation.

## Test layout
Prefer: tests/core/, tests/runtime/, tests/saas/, tests/adapters/, tests/integration/.
Legacy test roots are migrated incrementally. No test is deleted until its behavior is either migrated or proven obsolete.

## Import policy
Package __init__.py files must be lightweight namespaces.
Do not instantiate database clients, queues, FastAPI applications, Supabase clients, or production stores during ordinary package import.
Production composition belongs in explicit runtime entrypoints.

## Phase 5.2 optimization
Preparation is performed once per immutable input.
raw input -> PreparedResearchData -> multiple feature-set evaluations
Do not rebuild identical source transformations for each feature set.

## CI optimization
CI must distinguish changed-file validation, affected-subsystem validation, mandatory security/integrity gates, and full release validation.
Duplicate pytest/ruff work between jobs should be removed where the same artifact is already validated.

## Deletion policy
Deletion is reference-driven.
1. inventory import/reference sites; 2. identify canonical replacement; 3. migrate callers; 4. run affected tests; 5. remove obsolete tests; 6. delete legacy module; 7. run package/import smoke tests; 8. run PR gate.
Never delete a module merely because it looks old.

## Success metrics
Architecture v2 is successful when:
- a one-file Core change does not import SaaS;
- a Core test does not initialize Supabase;
- targeted tests run in seconds rather than minutes;
- Phase 5.2 shared preparation happens once;
- local validation commands match documented scopes;
- full release validation remains unchanged in strength;
- duplicate/legacy modules are measurably reduced.