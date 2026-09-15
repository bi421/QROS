# Canonical Quant Engine Ownership

**Status: architecture contract — documentation only**

This document intentionally makes **no code migration and no deletion**. It records ownership before any future migration work.

## Decision

| Area | Canonical owner | Role | Status |
|---|---|---|---|
| Public/domain quant API | `researchos/quant_engine/` | Python models, backend interface, simulation and research-facing integration | **CANONICAL** |
| Native C++ acceleration | `cpp_quant_engine/` | C++ implementation and Python/native bridge used to accelerate the canonical API | **CANONICAL NATIVE IMPLEMENTATION** |
| `cpp_quant/` | none | Historical/legacy naming; must not receive new implementation | **LEGACY / FORBIDDEN FOR NEW CODE** |
| `cpp_quant_engine_archive/` | none | Historical archive only | **ARCHIVE** |

## Why

Current integration tests import the Python quant backend from `researchos.quant_engine` while the native adapter is loaded from `cpp_quant_engine`. The C++ tree therefore complements the Python canonical API; it does not define a second public quant domain.

The repository already contains tests comparing the Python and C++ backends. Those tests are compatibility evidence, not permission to create another engine tree.

## Rules

1. New quant-domain behavior goes into `researchos/quant_engine/` unless the behavior is specifically native C++ implementation detail.
2. Native performance work belongs under `cpp_quant_engine/`.
3. Do not create a new `cpp_quant/` tree.
4. Do not create another quant engine package with a near-duplicate name.
5. Before adding a new engine/module/script, search the repository for an existing implementation and record the result.
6. Any migration, deletion, or rename requires a separate, narrowly scoped PR that updates this document and the compatibility tests together.
7. This document is the first source to consult when an AI session encounters `cpp_quant`, `cpp_quant_engine`, or `researchos/quant_engine`.

## Non-goal

This document does **not** prove that every historical quant implementation has already been removed. It establishes the target ownership boundary so future work can be evaluated against one stable architecture.
