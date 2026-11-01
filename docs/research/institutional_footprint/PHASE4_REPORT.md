# Phase 4 Report - Temporal and Replay Audit

**Study ID:** IFE1-2026-11-02
**Phase:** 4 - Temporal and replay audit
**Status:** PARTIAL - synthetic audit primitives pass; end-to-end phase gate remains open

## 1. Implemented audit primitives

Added researchos/quant_engine/order_flow/audit.py.

- Canonical serialization supports immutable dataclasses, enums, UTC timestamps, exact Decimal strings, mappings, and sequences. Floating-point values are rejected rather than silently rounded.
- build_replay_audit canonicalizes per-stream sequence order under an explicit policy and hashes canonical events, replay configuration, adapters, partitions, and code revision.
- Replay validation fails closed for missing/non-integer sequence numbers, duplicate sequence numbers, duplicate raw-event hashes within a stream, sequence gaps, negative sequences, event-time regression, and receive-time regression.
- audit_prefix_invariance selects input events by receive time (the point at which the process could know them), then compares outputs available by cutoff T from prefix-only replay and full replay.
- build_lineage_record hashes a derived output and records sorted raw input hashes, detector definition hash, code revision, latest input event time, latest input availability time, and output availability time. It rejects invalid hashes and look-ahead timestamps.

## 2. Detector hardening found during audit

The audit review exposed Phase 3 weaknesses; these were corrected and covered by adversarial tests.

- D01 now requires the reference to identify the same exact instrument and session as the scored trade. The caller must provide a session mapping derived from an explicit trading calendar; missing session mapping fails closed. A reference for MGC or ETH cannot qualify a GC or RTH trade.
- D02 now partitions clusters by exact instrument, session, source, dataset, and cohort. A cluster cannot bridge a session boundary or combine unrelated source/cohort streams.
- D06 now requires enough qualifying support windows, keeps exchange-flag and quote-inferred evidence separate, and rejects overlapping or cross-source support windows.
- D08 now binds trade-through evidence to the same instrument as its pre-existing reference, requires a raw trade hash, validates UTC timestamps, finite positive prices/quantity, and tick alignment.
- D08 window-end state labels are explicit: RECLAIMED_REFERENCE_BY_WINDOW_END, REMAINS_BEYOND_REFERENCE_AT_WINDOW_END, or AT_REFERENCE_AT_WINDOW_END. A touch exactly at the level is no longer mislabeled as acceptance. These are endpoint observations, not proof of sustained acceptance or rejection.

## 3. Synthetic adversarial validation

- Replay digest invariant to input permutation when per-stream integer sequence numbers are valid.
- Replay digest changes when replay configuration or code revision changes.
- Missing/non-integer, duplicate, gapped, negative, or time-regressing sequence streams are rejected.
- Future-received quotes cannot reclassify an earlier trade.
- A deliberately leaky replay that changes a historical output after a future event is appended is detected by prefix-invariance comparison.
- Lineage output and metadata hashes are deterministic; invalid hashes and output availability earlier than latest input availability are rejected.
- D01 cross-instrument and cross-session reference, D02 cross-session cluster, D06 mixed-source evidence, and D08 mismatched instrument/off-tick/at-level cases are covered.

## 4. Verification evidence

- Historical Phase 1-4 and Market Structure regression suite at the prior commit: **131 passed**.
- Phase 4 continuation focused suite (audit, mutation ledger, contracts, features, detectors): **71 passed**.
- Targeted Ruff check and format check for the changed order-flow package and new tests: PASS.
- Full repository Ruff check: PASS.
- Ruff format check on changed Python files: PASS.
- Full repository pytest suite after this continuation: **4684 passed, 41 skipped, 3 warnings** in 342.47 seconds.
- Git diff check: PASS.
- No live feed, licensed market data, broker connection, XAUUSD CFD tick volume, or real COMEX data was used.

The tests establish synthetic implementation behavior only. They do not establish real-market detector accuracy or predictive value. The three warnings are existing dependency deprecations in FastAPI/Starlette and a NumPy timedelta conversion in a Phase 5.2 provenance test; no test failed.

## 5. Explicit remaining blockers - Phase 4 is not yet complete

1. A source-specific sequence-policy framework is now implemented: CONTIGUOUS and MONOTONIC modes, explicit string-sequence-to-integer ordinal adapters, and explicit per-event partition IDs for sequence-reset epochs. The default remains strict contiguous integer sequences. No actual vendor adapter or vendor sequence contract has been verified; a caller must supply an adapter/policy grounded in that vendor's documentation.
2. A correction-aware trade mutation ledger now models NEW, CORRECT, and CANCEL revisions. Corrections/cancels must reference the currently active raw trade hash; revisions must be contiguous within an explicit trade scope; corrected payload availability must equal mutation receive time; exact duplicate mutation hashes are idempotent; conflicting duplicate payloads fail closed. Vendor-specific bust/cancel/correction semantics still require a documented adapter before ingest.
3. Prefix invariance is a reusable audit helper, not yet wired into a single end-to-end detector replay pipeline. The caller supplies the replay function and output-availability accessor.
4. The lineage builder records caller-supplied input hashes and timestamps. It does not yet automatically derive complete raw-input lineage for every detector. D05/D06 especially still need full source-event hash and availability propagation.
5. D07 displayed-depth replenishment still requires L2 book reconstruction, sequence-gap invalidation, and snapshot recovery.
6. No licensed GC/MGC source, vendor semantics, or independent real-event labels have been accepted.

Therefore Phase 4 remains PARTIAL and Phase 5 real-data ingestion remains BLOCKED. The new mutation and sequence primitives are synthetic-only; they are not vendor conformance certification. Do not interpret this phase as proof that the detector suite is ready to identify institutional activity.

## 6. Next required work

Continue Phase 4 by wiring event-derived lineage into every detector output and integrating prefix-invariance plus deterministic replay into one end-to-end detector pipeline. Add vendor-specific sequence and mutation adapters only after source documentation is available. D07 still requires L2 reconstruction, sequence-gap invalidation, and snapshot recovery. Re-run full tests and the end-to-end replay gate before Phase 4 can be marked complete.


## 7. Phase 4 continuation - correction ledger and sequence policies

Implemented after the initial Phase 4 commit:

- TradeMutation represents NEW, CORRECT, and CANCEL events separately from positive-quantity TradeEvent records and includes an explicit trade scope to avoid assuming vendor trade IDs are globally unique. Corrections replace the currently active version; cancels remove it from the active snapshot.
- replay_trade_mutations requires per-trade contiguous revisions, current-version supersession hashes, non-regressing receive times, and exact identity matching. Exact repeated mutation payloads with the same raw hash are idempotent; a hash collision with a different payload is rejected.
- TradeMutation is accepted by deterministic replay auditing and participates in per-source/dataset/instrument/event-type stream validation.
- SequencePolicy supports CONTIGUOUS and MONOTONIC ordinal modes. String vendor sequences are not sorted lexicographically; they require an explicit raw-hash-to-integer ordinal adapter. Sequence resets require complete explicit per-event partition mapping, after which each partition is validated independently.
- Unknown policy keys, incomplete reset partitions, duplicate ordinals, gaps under CONTIGUOUS mode, and event/receive-time regressions fail closed.
- build_lineage_record_from_events derives input hashes and latest input clocks from actual immutable event objects rather than trusting caller-supplied hashes/timestamps.

These are reusable synthetic primitives. They do not establish a real vendor's sequence, correction, or cancel semantics. Detector outputs are not yet universally lineage-enveloped, and the complete detector pipeline is not yet under a single prefix-invariance replay gate.
