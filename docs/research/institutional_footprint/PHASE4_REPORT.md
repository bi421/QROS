# Phase 4 Report - Temporal, Replay, and Lineage Audit

**Study ID:** IFE1-2026-11-02
**Phase:** 4 - temporal and replay audit
**Status:** PARTIAL - synthetic audit gates pass; source-specific and production integration gates remain open

## 1. Deterministic replay and temporal audit

Implemented in `researchos/quant_engine/order_flow/audit.py`:

- Canonical serialization supports immutable dataclasses, enums, UTC timestamps, exact Decimal strings, mappings, and sequences. Floating-point values are rejected.
- `build_replay_audit` validates per-stream sequence policies, partitions, event-time ordering, receive-time ordering, duplicate identities, and sequence gaps. It hashes canonical events, replay configuration, adapters, partitions, and code revision.
- `audit_prefix_invariance` selects inputs by `receive_time_utc <= T`, then compares outputs available by T from prefix-only replay and full replay.
- `build_lineage_record_from_events` and `build_lineage_record_from_input_lineage` derive or consume event-derived input lineage and reject incomplete lineage and look-ahead availability.
- `audit_detector_pipeline` composes raw replay validation, prefix-only/full replay comparison, and output-lineage validation. Every output must expose a complete `InputLineage`, a valid detector definition ID, and an output-availability timestamp no earlier than its latest input.

The detector replay function and output accessors remain caller-supplied. This is a reusable audit gate, not yet a canonical production orchestrator that wires every detector automatically.

## 2. Event-derived lineage integration

Implemented in `lineage.py`, `features.py`, `detectors.py`, and `event_ledger.py`:

- Trade classification retains the supporting quote event payloads, rather than only a quote hash.
- Flow windows derive lineage from selected trades, supporting quotes, correction mutations, and historical replacement trade payloads.
- `TradeLedgerSnapshot` retains all applied mutation events and the full `NEW -> CORRECT` history for each active trade. `classify_trade_from_ledger` preserves that history through classification.
- `aggregate_trade_flow` accepts `additional_lineage_events` so callers can include relevant cancellation mutations even when the canceled trade is absent from the active-trade snapshot. The caller must select the relevant ledger events; this is not an automatic session/window adapter.
- D01 candidate lineage includes scored trade, quote evidence, correction history, historical trade payloads, and the size-reference lineage.
- D02 clusters combine member lineage and preserve incompleteness if any member lacks lineage.
- D05 carries flow, price-response, and volatility input lineage. Missing raw inputs remain explicitly incomplete.
- D06 carries support-window and contested-level lineage and rejects contested-level events from a different instrument.
- D08 carries reference, trade-through, response, and optional correction-history lineage. It rejects a response event that precedes the trade-through event.
- `build_lineage_record_from_input_lineage` refuses to certify any output whose lineage is incomplete.

Lineage completeness is not inferred from a hash alone. If the caller does not supply the raw event payloads needed to establish a dependency, the output remains incomplete and the pipeline audit gate rejects it.

## 3. Detector hardening retained from prior phases

- D01 requires exact instrument and session match between the scored trade and its reference. The caller supplies session mapping from an explicit calendar; missing mapping fails closed.
- D02 partitions clusters by exact instrument, session, source, dataset, and cohort.
- D06 requires enough qualifying support windows, keeps exchange-flag and quote-inferred evidence separate, and rejects overlapping or cross-source support windows.
- D08 requires a prior reference, an actual trade-through, valid UTC timestamps, finite positive prices/quantity, and tick alignment.
- D08 endpoint labels remain `RECLAIMED_REFERENCE_BY_WINDOW_END`, `REMAINS_BEYOND_REFERENCE_AT_WINDOW_END`, or `AT_REFERENCE_AT_WINDOW_END`. These are endpoint observations, not proof of sustained acceptance or rejection.
- D07 displayed-depth replenishment is not implemented; it requires L2 book reconstruction, sequence-gap invalidation, and snapshot recovery.

## 4. Synthetic adversarial validation

- Replay digest is invariant to input permutation when valid per-stream sequence metadata is supplied.
- Replay digest changes when replay configuration or code revision changes.
- Missing/non-integer, duplicate, gapped, negative, or time-regressing sequences are rejected under the applicable policy.
- Explicit string-sequence ordinal adapters and sequence-reset partitions are validated; no vendor adapter has been certified.
- Future-received quotes cannot reclassify an earlier trade; a deliberately leaky historical replay is detected by prefix-invariance comparison.
- Pipeline audit rejects incomplete output lineage and compares prefix-only versus full-replay historical outputs.
- Correction and cancel mutations are tested for revision ordering, supersession identity, idempotency, and conflicting hash payloads.
- Corrected trade history is preserved through classification and flow aggregation; canceled mutation events can be included in an otherwise empty flow window's lineage.
- D06 cross-instrument level lineage and D08 pre-trade response-event cases are rejected.
- D08 lineage tests confirm the original trade payload, corrected payload, mutation events, reference event, and response event are all retained.

## 5. Verification evidence

- Focused Phase 1-4 suite (audit, mutation ledger, features, detectors): **73 passed**.
- Full repository `pytest -q`: **4701 passed, 41 skipped, 3 warnings** in **180.24 seconds**; exit code 0.
- Full repository Ruff check: PASS.
- Ruff format check on changed order-flow package and related tests: PASS.
- `git diff --check`: PASS.
- The three warnings are existing FastAPI/Starlette deprecations and a NumPy timedelta conversion warning in a Phase 5.2 provenance test; no tests failed.
- No live feed, licensed market data, broker connection, XAUUSD CFD tick volume, or real COMEX data was used.

These results prove synthetic implementation behavior only. They do not prove real-market detector accuracy, institutional identity, or predictive value.

## 6. Remaining blockers - Phase 4 remains PARTIAL

1. **Vendor sequence semantics:** CONTIGUOUS and MONOTONIC policies, explicit string-to-ordinal adapters, and explicit reset partitions exist. Actual vendor sequence semantics and adapters remain unverified until source documentation is available.
2. **Vendor correction semantics:** the generic NEW/CORRECT/CANCEL ledger is synthetic-only. Vendor-specific bust, correction, cancel, and trade-ID scope rules require documented adapters.
3. **Production detector orchestration:** `audit_detector_pipeline` provides the combined gate, but the actual detector replay callback and availability/definition accessors remain caller-supplied. A single canonical pipeline that automatically runs and audits all detector stages is not yet wired.
4. **Caller-supplied lineage dependencies:** reference samples, price-response inputs, volatility inputs, contested-level inputs, and relevant cancellation events must be supplied by the integration layer. Missing dependencies deliberately block lineage certification.
5. **D07 L2 book reconstruction:** displayed-depth replenishment remains unimplemented pending valid L2 snapshots, incremental updates, sequence-gap invalidation, and recovery semantics.
6. **Real data and independent labels:** no licensed GC/MGC trade/quote/L2 feed or independent real-event labels have been accepted. Real detector precision/recall and market usefulness are therefore unknown.

**Phase 5 real-data ingestion remains BLOCKED.** Do not interpret the synthetic test results as proof that the engine can identify named institutions, beneficial owners, hidden orders, or profitable trades.

## 7. Next required work

- Wire a canonical detector replay orchestrator to `audit_detector_pipeline`; require complete raw-event lineage and explicit output availability for every emitted candidate.
- Add source-specific sequence and correction adapters only after the chosen vendor's documentation and license terms are reviewed.
- Implement D07 only with valid L2 reconstruction, sequence-gap invalidation, and snapshot recovery.
- Obtain licensed GC/MGC data and independent event labels before measuring real-world detector accuracy.
- Keep strategy research separate, preregistered, cost-aware, and out-of-sample. No order execution is in scope.
