# Phase 1 Report — Institutional Footprint Engine

**Study ID:** `IFE1-2026-11-02`
**Phase:** `1 — Immutable contracts and synthetic fixtures`
**Status:** `PASS — CONTRACTS ONLY`
**Code revision at report creation:** recorded by Git commit below.

## Scope completed

Added `researchos/quant_engine/order_flow/` as an isolated, read-only research package. No existing Market Structure implementation was changed.

Implemented immutable, frozen/slotted contracts for:

- `InstrumentMetadata`: exact contract identity, currency, tick size/value, multiplier.
- `DatasetManifest`: source/vendor/venue/product, exact instrument, feed type, coverage, calendar/timezone, timestamp and sequence semantics, aggregation/aggressor/correction/recovery semantics, license reference/status, raw artifact URI/hash, schema and acquisition revision, known exclusions, optional vendor documentation hash.
- `TradeEvent`: event/receive timestamps, Decimal price/quantity, optional native sequence/trade IDs, explicit aggressor side and classification method.
- `QuoteEvent`: bid/ask prices, optional displayed sizes, quote condition, timestamps and optional sequence.
- `L2BookEvent`: sequence, price level, side, operation, quantity and snapshot/delta event kind.
- Explicit enums for feed type, license status, aggressor side/method, quote condition, book side/operation/event kind, and data-quality state.

## Fail-closed rules implemented

- All timestamps must be timezone-aware UTC; receive time cannot precede event time.
- Price/quantity values must be finite `Decimal` values; positive or nonnegative constraints are enforced by field semantics.
- Raw artifact/event hashes must be lowercase 64-character SHA-256 hex.
- Aggressor side defaults to UNKNOWN; a classified side requires an explicit method and vice versa.
- Locked/crossed quote conditions must agree with bid/ask prices.
- L2 DELETE requires zero quantity; ADD/CHANGE require positive quantity.
- Contract tick alignment and instrument identity are checked explicitly.
- Dataset manifest validates event source, dataset, instrument, feed type, and coverage range.
- A manifest is eligible for real-data research only when license status is VERIFIED. `NOT_REQUIRED` and `UNVERIFIED` do not pass this gate.

## Tests and checks

- New contract tests: `15 passed`.
- Combined new contracts + existing market-structure definition/adapter/detector tests: `90 passed in 3.14s`.
- Ruff lint: PASS.
- Ruff formatting applied to the new package and test file.
- `git diff --check`: PASS before commit.
- Python package imports: PASS.

## Explicitly not implemented

- No feed connection, downloader, vendor API, or real market data.
- No sequence-gap reconstruction/recovery state machine yet.
- No trade aggressor inference, Delta/CVD, footprint aggregation, L2 book reconstruction, or detectors.
- No Supabase migration or storage changes.
- No strategy, trade signals, backtest, or execution.

## Phase 1 acceptance

The immutable event/manifest contracts and synthetic unit fixtures are implemented. Existing Market Structure tests remain green. This is a contract-level PASS only; it does not certify feed completeness, licensed data availability, real-world detector accuracy, or predictive edge.

## Next phase

Phase 2: deterministic synthetic-only trade/quote feature engine (aggressor-side handling, signed/unknown quantity accounting, Delta, CVD, explicit session reset definitions, and price-response inputs). Continue to block real-data ingestion until Phase 5 source/license gates are independently verified.
