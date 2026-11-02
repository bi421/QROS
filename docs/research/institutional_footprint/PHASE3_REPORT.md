ï»¿# Phase 3 Report â€” Institutional Footprint Candidate Detectors

**Study ID:** `IFE1-2026-11-02`
**Phase:** `3 â€” Deterministic candidate detectors`
**Status:** `PASS â€” SYNTHETIC ONLY`

## Implemented

Added `researchos/quant_engine/order_flow/detectors.py` and exported the public API.

### D01 â€” Unusually large print

- Consumes a per-trade `SizeReference` supplied by an upstream reference builder.
- Requires a cohort percentile at or above the frozen definition threshold, a minimum reference count, and a trade quantity at or above the supplied quantity threshold.
- Requires `reference_end_utc` to be strictly earlier than the trade event time; same-time and future references fail closed.
- Retains cohort, percentile, sample count, reference end time, side-classification method, and definition hash in the candidate.
- Important limitation: Phase 3 does not calculate rolling percentiles or cohort baselines. The upstream reference builder and its historical-only semantics remain a separate prerequisite and are not yet implemented or independently verified.

### D02 â€” Large-print cluster

- Builds deterministic, non-overlapping clusters from D01 candidates.
- Uses a fixed event-time window anchored at the first candidate in a cluster.
- Groups by exact instrument, then event time and trade hash for deterministic ordering.
- Reports BUY, SELL, and UNKNOWN quantities separately. Mixed/unknown-side clusters remain `UNKNOWN` rather than being forced into a directional label.

### D05 â€” Aggression versus price response

- Uses exchange aggressor flags and quote-inferred aggressor flow as separate input streams; it never blends the two for one detector result.
- Applies a declared classified-quantity coverage floor; inadequate coverage returns `INSUFFICIENT_DATA`.
- Reports raw price progress in ticks and normalized progress in trailing-volatility units.
- Requires the volatility estimate's UTC `as_of` time to be no later than the flow window start.
- States are descriptive (`HIGH_AGGRESSION_HIGH_PROGRESS`, `HIGH_AGGRESSION_LOW_PROGRESS`, `LOW_AGGRESSION_HIGH_PROGRESS`, `OTHER`, `INSUFFICIENT_DATA`), not trade signals.
- The volatility estimate itself is supplied by the caller; a past-only volatility estimator is not implemented in this phase.

### D06 â€” Absorption candidate

- Requires repeated level tests and high directional aggression with constrained normalized price progress.
- Requires the contested level's availability timestamp to precede the supporting flow windows.
- Labels the result `TRADE_PRICE_ABSORPTION_PATTERN`. Without reconstructed L2 evidence it does not claim displayed-book replenishment, iceberg activity, hidden orders, or an identified institution.
- The level-touch counter is supplied by the caller; a validated touch-counting adapter is not implemented in this phase.

### D08 â€” Liquidity sweep candidate

- Requires a reference level available before the trade-through event, a nonzero trade-through quantity, and a bounded post-event response window.
- Records direction relative to the reference and the bounded window-end state as RECLAIMED_REFERENCE_BY_WINDOW_END, REMAINS_BEYOND_REFERENCE_AT_WINDOW_END, or AT_REFERENCE_AT_WINDOW_END; these endpoint observations are not proof of sustained acceptance or rejection.
- The reported elapsed time is the post-event response-window duration, not the exact duration price remained beyond the level.
- The reference-level adapter and trade-through event extraction are caller responsibilities; a wick-only OHLC pattern is insufficient.

## Determinism and provenance

- Detector definitions are immutable and produce a deterministic SHA-256 `definition_id` from their thresholds and windows.
- D01 reference timestamps, D05 volatility `as_of`, D06 level-availability time, and D08 level-availability time enforce key no-lookahead boundaries.
- No detector identifies a bank, fund, institution, beneficial owner, parent order, stop order, or motive.
- No composite confidence score is produced; correlated features are not double-counted into a synthetic certainty score.

## Validation

- Synthetic candidate-detector tests: 9.
- Combined Phase 1 contract, Phase 2 feature, Phase 3 detector, and existing Market Structure definition/adapter/detector tests: **113 passed**.
- Ruff lint: PASS.
- Ruff formatting: PASS.
- No live feed, licensed market data, broker connection, XAUUSD CFD tick volume, or real COMEX data was used.

## Not implemented / blocked

- D03 dedicated aggressive-flow cluster detector (source-separated flow features exist in Phase 2, but no separate cluster event is emitted yet).
- D07 displayed-depth replenishment; requires valid L2 book reconstruction and sequence-gap recovery.
- Historical cohort reference builder and past-only volatility estimator.
- Confirmed swing-level / touch-count / trade-through adapters.
- Composite footprint evidence aggregation.
- Real-feed adapter, licensing/provenance verification, independent detector precision/recall labels.
- Follow strategy, entries/exits, risk sizing, P&L optimization, or order execution.

## Interpretation and phase gate

Phase 3 proves only deterministic behavior on synthetic fixtures. It does not prove detector accuracy on real markets, identify institutions, or establish predictive value. The current FTMO-Demo XAUUSD OHLC/tick-volume dataset remains unsuitable for trade-level Delta/CVD or institutional-footprint claims and was not used. GC/MGC futures and OTC XAUUSD CFD remain distinct instruments/venues.

Phase 4 should focus on temporal/replay audit and adversarial fixtures, then Phase 5 must independently establish licensed, complete, sequence-correct GC/MGC trade and quote data before any real-data evaluation.
