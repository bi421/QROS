# Phase 4 Report - Temporal and Replay Audit

**Study ID:** IFE1-2026-11-02
**Phase:** 4 - Temporal and replay audit
**Status:** PARTIAL - synthetic audit primitives pass; end-to-end phase gate remains open

## 1. Implemented audit primitives

Added researchos/quant_engine/order_flow/audit.py.

- Canonical serialization supports immutable dataclasses, enums, UTC timestamps, exact Decimal strings, mappings, and sequences. Floating-point values are rejected rather than silently rounded.
- build_replay_audit canonicalizes per-stream integer sequence order and hashes canonical events, replay configuration, and code revision.
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

- Focused Phase 1-4 and Market Structure regression suite: **131 passed**.
- Full repository Ruff check: PASS.
- Ruff format check on changed Python files: PASS.
- Full repository pytest suite: **4669 passed, 41 skipped, 3 warnings** in 391.78 seconds.
- Git diff check: PASS.
- No live feed, licensed market data, broker connection, XAUUSD CFD tick volume, or real COMEX data was used.

The tests establish synthetic implementation behavior only. They do not establish real-market detector accuracy or predictive value. The three warnings are existing dependency deprecations in FastAPI/Starlette and a NumPy timedelta conversion in a Phase 5.2 provenance test; no test failed.

## 5. Explicit remaining blockers - Phase 4 is not yet complete

1. The replay validator supports only documented contiguous integer sequences. Vendor-specific string sequences, resets, partition epochs, and sequence semantics need explicit adapters/policies. The caller must partition a sequence-reset stream before replay.
2. Correction/cancel events are not represented by the current event contracts. Duplicate raw hashes are rejected; there is no correction-aware idempotent event ledger yet.
3. Prefix invariance is a reusable audit helper, not yet wired into a single end-to-end detector replay pipeline. The caller supplies the replay function and output-availability accessor.
4. The lineage builder records caller-supplied input hashes and timestamps. It does not yet automatically derive complete raw-input lineage for every detector. D05/D06 especially still need full source-event hash and availability propagation.
5. D07 displayed-depth replenishment still requires L2 book reconstruction, sequence-gap invalidation, and snapshot recovery.
6. No licensed GC/MGC source, vendor semantics, or independent real-event labels have been accepted.

Therefore Phase 5 real-data ingestion remains BLOCKED. Do not interpret this phase as proof that the detector suite is ready to identify institutional activity.

## 6. Next required work

Continue Phase 4 by wiring input hashes and availability timestamps into every detector output, defining correction/cancel semantics, and implementing source-specific sequence policies. Re-run prefix-invariance and deterministic replay against the complete detector pipeline. Only after those checks pass should Phase 4 be marked complete.
