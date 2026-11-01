# Institutional Footprint Engine — Research Specification

**Study ID:** `IFE1-2026-11-02`
**Version:** `0.1.0`
**Status:** `PHASE0_DRAFT — SYNTHETIC IMPLEMENTATION ONLY`
**Purpose:** Detect observable market footprints consistent with unusually large or persistent participants in centralized gold futures data. This engine does not identify legal entities, beneficial owners, funds, banks, or a specific institution.

## 1. Research objective

Build a deterministic, reproducible, read-only engine that detects and records unusually large executed activity and its subsequent interaction with displayed liquidity and price. The engine must separate:

1. **Observed event:** directly present in validated source data.
2. **Derived measurement:** deterministic calculation from observed events.
3. **Footprint hypothesis:** a defined pattern consistent with large/persistent participation, absorption, replenishment, or liquidity-taking.
4. **Unknown:** participant identity, motive, parent order, inventory, and activity outside the observed venue/feed.

The engine is a detector and evidence generator, not a trading strategy. Strategy design is a later, separately preregistered study after detector validation.

## 2. Scope and exclusions

### In scope for V1

- Centralized exchange-traded gold futures (GC and/or MGC), with exact contract identity and roll handling recorded.
- Trade-level prints with exchange timestamps, price, quantity, sequence/trade identifiers where provided.
- Best bid/ask quote events for aggressor-side classification and spread context.
- L2 market-by-price depth only when licensed and available with documented update semantics.
- Large-trade activity, repeated aggressive activity, price impact/efficiency, absorption candidates, displayed-liquidity replenishment candidates, and sweep candidates.
- Event-time causal ordering, replay, provenance, deterministic outputs, and explicit unknown states.

### Explicitly out of scope

- Identifying a named institution or inferring account identity.
- Claiming that a large print is necessarily institutional, informed, or directional.
- Treating spoofing, iceberg orders, hidden liquidity, or intent as directly observed from incomplete public feeds.
- Generating BUY/SELL entries, targets, stops, position sizing, or execution instructions.
- Live order routing, broker credentials, trading APIs, or automatic execution.
- Treating XAUUSD CFD tick volume as exchange trade volume or deriving true bid/ask delta from OHLC bars.
- Treating GC/MGC activity as identical to OTC XAUUSD activity.

## 3. Instrument and source hierarchy

Primary research venue: CME/COMEX gold futures. Instrument selection (GC vs MGC), contract month, exchange product code, tick size/value, multiplier, trading calendar, and roll methodology must be fixed in the dataset manifest before real-data ingestion.

Source requirements, highest to lowest:

1. Exchange-authorized trade feed with trade price, quantity, exchange event time, and sequence/trade identifiers.
2. Exchange-authorized quote feed with bid/ask prices and timestamps; displayed sizes where supplied.
3. Exchange-authorized market-by-price L2 incremental updates with sequence numbers and snapshot/recovery semantics.
4. Broker/terminal historical bars for price-context comparison only; never as a substitute for trade prints or L2.

A vendor feed is not considered exchange-complete merely because it labels data as futures. Record vendor, product, license, venue coverage, aggregation, timestamp semantics, correction/cancel handling, depth level, update mode, and known exclusions.

## 4. Core event taxonomy

All detector outputs are candidates, not assertions about actor identity:

- `UNUSUALLY_LARGE_TRADE`
- `LARGE_TRADE_CLUSTER`
- `AGGRESSIVE_BUY_CLUSTER`
- `AGGRESSIVE_SELL_CLUSTER`
- `BUY_ABSORPTION_CANDIDATE`
- `SELL_ABSORPTION_CANDIDATE`
- `BID_REPLENISHMENT_CANDIDATE`
- `ASK_REPLENISHMENT_CANDIDATE`
- `BUY_SIDE_LIQUIDITY_SWEEP_CANDIDATE`
- `SELL_SIDE_LIQUIDITY_SWEEP_CANDIDATE`
- `HIGH_AGGRESSION_LOW_PRICE_PROGRESS`
- `LOW_AGGRESSION_HIGH_PRICE_PROGRESS`
- `INSUFFICIENT_DATA`

Each event carries source/dataset IDs, instrument/contract, event-time interval, detector definition ID, input lineage, quality flags, observed measurements, supporting evidence, contradictory evidence, and limitations.

## 5. V1 detector definitions (draft; freeze before real data)

### 5.1 Unusually large trade

Measure trade quantity against a preregistered, instrument- and session-aware historical reference distribution. Report absolute quantity, percentile, robust standardized score, and reference sample size. Do not choose thresholds by inspecting future outcomes. A large trade is not automatically an institutional trade.

### 5.2 Large trade cluster

Detect a concentration of unusually large prints within a fixed event-time window. Record total quantity, print count, side-known quantity, inter-arrival distribution, and fraction of venue volume only when the feed is demonstrably complete for that measure.

### 5.3 Aggressive activity

Classify trades using exchange-provided aggressor flags when their semantics are documented. Otherwise infer side only from synchronized quotes using a preregistered quote test. Ambiguous, stale-quote, locked/crossed-market, and out-of-sequence trades remain `UNKNOWN`; do not force-classify them. Keep `EXCHANGE_FLAG` and `QUOTE_INFERRED` labels distinct.

### 5.4 Delta and CVD

`delta = classified_buy_aggressor_quantity - classified_sell_aggressor_quantity` per declared aggregation interval. Unknown-side quantity is reported separately and excluded from signed delta. CVD reset/anchoring is an explicit immutable definition (session, trading day, or continuous); V1 must not silently mix reset conventions. Report classified-side coverage alongside delta/CVD.

### 5.5 Price response / impact efficiency

Measure price change and favorable/adverse excursion over fixed, preregistered event-time and trade-count horizons, normalized by volatility/tick size where appropriate. Do not infer passive absorption from low price progress alone; require separate evidence of sustained aggressive flow and, for replenishment claims, valid L2 updates.

### 5.6 Absorption candidate

Require (a) unusually elevated classified aggressive quantity on one side, (b) limited price progress in that direction under a frozen normalization, and (c) a preregistered persistence or repeated-test condition. L2 displayed-liquidity replenishment may strengthen the evidence but is not assumed. The event is a candidate, not proof of a hidden/iceberg order or a specific passive participant.

### 5.7 Replenishment candidate

Only available with valid L2 incremental updates and reconstructable book state. Define price-level queue/depth depletion followed by displayed size restoration within a fixed interval, with sequence continuity and snapshot recovery verified. Public market-by-price data may not reveal individual order identity; call this displayed-depth replenishment, not iceberg detection.

### 5.8 Liquidity sweep candidate

Require a predeclared reference level, observable trade-through beyond it, and a specified subsequent price response. A candle wick alone is insufficient. Keep stop-trigger causality and participant intent unknown unless independently observed.

## 6. Data-quality states

Every interval is classified as one of:

- `VALID`: all required fields and sequence/timestamp checks pass.
- `DEGRADED`: explicitly bounded noncritical omissions; affected metrics carry coverage limitations.
- `INVALID`: corrupt ordering, unresolved sequence gap, invalid book state, or invalid contract metadata.
- `STALE`: source latency exceeds preregistered tolerance.
- `UNAVAILABLE`: required feed or field is absent.

Fail closed: no detector requiring a missing/invalid field may emit a positive event. It must emit `INSUFFICIENT_DATA` or a blocked status with machine-readable reason codes.

## 7. Temporal integrity

- Store exchange/event time and local receive time separately, both timezone-aware UTC.
- Preserve source sequence and correction/cancel semantics.
- Do not reorder events silently. A reorder buffer, if required by feed semantics, must be specified and versioned.
- No future event may contribute to a feature or detector output timestamped earlier.
- For quote-based aggressor classification, use only a valid quote available at or before the trade event according to the source's documented clock/sequence semantics.
- L2 book reconstruction requires valid snapshot baseline and contiguous updates; after unresolved sequence loss, invalidate the book until a valid snapshot recovery.
- Contract rolls are explicit boundaries; never concatenate contracts as if fungible without a registered adjustment/roll rule.

## 8. Determinism and lineage

Every detector definition is immutable and SHA-256 identified from canonical serialized configuration. Every output records dataset SHA, source manifest SHA, code revision, definition ID, input event range, output hash, and run configuration. Same bytes + same code + same definitions must reproduce identical results.

## 9. Research and evaluation boundaries

Phase 0/1/2 development uses synthetic fixtures only. Historical real-data exploration, if later authorized, must be separately labelled exploratory and cannot be called independent confirmation. Detector validation labels must be defined independently of the detector outputs. Do not tune thresholds on the prospective holdout. A separate strategy preregistration is required before testing whether detected footprints can be followed profitably.

## 10. Decision states

- `BLOCKED_DATA_SOURCE`: required licensed source not available/verified.
- `INSUFFICIENT_EVIDENCE`: sample, coverage, labels, or quality insufficient.
- `DETECTOR_VALIDATED`: detector meets preregistered event-detection/reproducibility criteria only.
- `NO_RELIABLE_FOOTPRINT_FOUND`: valid study completed but no detector meets criteria.

`DETECTOR_VALIDATED` does not mean profitable, predictive, institutional identity confirmed, or suitable for trading.

## 11. Phase gates

- Phase 0: requirements, source contract, detector definitions, validation plan; documentation only.
- Phase 1: immutable contracts and synthetic fixtures.
- Phase 2: deterministic trade/quote feature engine and unit tests; synthetic only.
- Phase 3: detector implementations and adversarial synthetic tests; synthetic only.
- Phase 4: event replay, temporal/leakage and quality audits; synthetic only.
- Phase 5: licensed real-data adapter and provenance audit, only after source/license/data gates.
- Phase 6: preregistered detector validation; no strategy optimization.
- Phase 7: separate strategy research to follow validated detector events.

Stop after each phase and report evidence before crossing the next gate.
