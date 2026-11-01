# Phase 2 Report — Institutional Footprint Engine

**Study ID:** `IFE1-2026-11-02`
**Phase:** `2 — Deterministic trade/quote feature engine`
**Status:** `PASS — SYNTHETIC ONLY`

## Implemented

Added `researchos/quant_engine/order_flow/features.py` and exported its public API.

### 1. Aggressor-side classification

- Preserve documented exchange aggressor flags as a distinct source.
- Quote inference is used only when no exchange classification is present.
- The selected quote must match the exact instrument, have an earlier event timestamp, and have been received no later than the trade's receive time.
- Equal-timestamp quote candidates are treated as ambiguous.
- Stale, locked, crossed, unavailable, late-received, or otherwise noncausal quotes fail closed to UNKNOWN.
- Trade at/above ask is classified BUY; trade at/below bid is classified SELL; trade inside spread remains UNKNOWN.
- Exchange-flag and quote-inferred methods remain separately attributable in the resulting measurements.

### 2. Flow aggregation

For a declared instrument, session, and half-open event-time interval `[start, end)`, calculate:

- Total, BUY, SELL, and UNKNOWN quantity.
- Total, classified, and unknown trade counts.
- Exchange-flag BUY/SELL quantities and delta.
- Quote-inferred BUY/SELL quantities and delta.
- Combined delta.
- Classified-side quantity coverage.

UNKNOWN quantity remains in the total-volume denominator and is excluded from signed delta. Empty intervals return zero delta and zero coverage; they do not fabricate a direction.

### 3. CVD

- CVD is the cumulative sum of the declared flow-window deltas.
- It resets whenever the supplied session identifier changes.
- Input windows must be chronological and non-overlapping.
- The engine rejects out-of-order windows instead of silently sorting or repairing them.

### 4. Price response input

Added signed price progress in exact contract ticks, using contract tick metadata. This is a descriptive measurement only; it is not a forward return, prediction, or trading signal.

## Validation

- New institutional-footprint contract + feature tests: 29 passed.
- Combined with existing Market Structure definition/adapter/detector tests: **104 passed in 2.06s**.
- Ruff lint: PASS.
- Ruff formatting: PASS.
- Package exports/imports: PASS.
- No market data, broker feed, vendor API, or live connection was used.
- No detector thresholds or strategy parameters were optimized.

Synthetic fixture assertions cover exchange-flag preservation, quote-based BUY/SELL, inside-spread UNKNOWN, stale/locked/ambiguous/noncausal quotes, unknown-volume coverage, source-separated deltas, half-open intervals, exact instrument filtering, session CVD reset, overlap/order rejection, and tick-normalized price progress.

## Interpretation boundary

This phase measures observable executed aggressor flow and its price context. It does **not** identify a bank, fund, institution, parent order, beneficial owner, or motive. A large BUY delta is not proof that one large institution is accumulating, and it does not imply that price must rise. Exchange-flag and quote-inferred measurements must remain distinguishable when interpreting any later footprint candidate.

The current FTMO-Demo XAUUSD OHLC/tick-volume dataset remains incompatible with true trade-level Delta/CVD. It was not used here.

## Not implemented

- Historical rolling reference distributions or unusual-size thresholds.
- Large-trade/cluster/absorption/sweep detectors.
- L2 order-book reconstruction or replenishment.
- Real-feed adapters, sequence-gap recovery, or independent vendor/license verification.
- Any BUY/SELL trading strategy or execution.

## Phase gate

Phase 2 is complete at the deterministic synthetic feature layer. Phase 3 may implement candidate detectors against these features, still using synthetic fixtures only. Real-data ingestion remains blocked until the source, license, completeness, and provenance gates in Phase 5 are independently satisfied.
