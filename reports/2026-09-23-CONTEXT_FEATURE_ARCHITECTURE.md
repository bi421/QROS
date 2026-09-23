# Phase 5.2 Rebuild — Context Feature Architecture

## Purpose

Pre-research observations may initialize rolling feature state without becoming research samples.

## Boundary

- Context rows are strictly before the research start day.
- At least `warmup=60` context observations are required.
- Feature state is computed chronologically over `context + research`.
- Only research rows are emitted.
- Research labels use the existing forward horizon (`horizon=5`).
- Therefore, with sufficient context, emitted research rows are `research_rows - 5`, not `research_rows - 60 - 5`.

## Leakage rule

Context is historical state only. No context row is emitted, labeled, trained, or scored. No future research observation may affect an earlier feature row.

## Scientific gate

This architecture does **not** accept a context source automatically. Dukascopy context must first pass a separate source-continuity validation against the canonical research source over an adequate overlap. Only accepted context may initialize the feature state.

## Current real-data implication

The canonical four-way research dataset has 1246 common days. The previous implementation discarded 60 warm-up rows from the research sample itself and therefore reported 1181 usable rows. The context-aware architecture is intended to preserve the research-period rows while using pre-research observations solely for feature initialization. The expected research-period label-eligible count is therefore 1241, provided source validation and context coverage both pass.

No model result is valid until those gates are explicitly passed.
