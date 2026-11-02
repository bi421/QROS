# Institutional Footprint Engine — Data Contract

**Version:** `0.1.0` — draft; synthetic implementation only.

## 1. Dataset manifest (required)

- `dataset_id`, `dataset_version`, `source_id`, `vendor`, `venue`, `product_code`.
- `instrument_root`, `contract_month`, `contract_id`, `currency`, `tick_size`, `tick_value`, `multiplier`.
- `coverage_start_utc`, `coverage_end_utc`, `trading_calendar_version`, `timezone`.
- `feed_type` (`TRADES`, `TOP_OF_BOOK`, `L2_MARKET_BY_PRICE`, `BARS`).
- `timestamp_semantics`, `sequence_semantics`, `aggregation_semantics`.
- `aggressor_side_semantics`, `correction_cancel_semantics`, `snapshot_recovery_semantics`.
- `license_reference`, `license_status`, `known_exclusions`, `vendor_documentation_hash`.
- `raw_artifact_uri`, `raw_artifact_sha256`, `schema_version`, `acquisition_code_revision`.

No real feed may be accepted with unknown instrument identity, timestamp semantics, or licensing status.

## 2. Trade event schema

| Field | Type | Required | Notes |
|---|---|---:|---|
| source_id | string | yes | Stable source identity |
| dataset_id | string | yes | Immutable dataset version |
| instrument_id | string | yes | Exact contract, not just root |
| event_time_utc | aware datetime | yes | Exchange/source event time |
| receive_time_utc | aware datetime | yes | Local ingest time |
| sequence_number | int/string | conditional | Preserve source-native type |
| trade_id | string | conditional | If source provides it |
| price | finite decimal | yes | Tick-aligned per contract |
| quantity | positive integer/decimal | yes | Preserve source units |
| aggressor_side | enum | no | BUY/SELL/UNKNOWN |
| aggressor_method | enum | yes | EXCHANGE_FLAG / QUOTE_INFERRED / UNKNOWN |
| event_action | enum | conditional | NEW/CORRECT/CANCEL if supported |
| raw_event_hash | hex SHA-256 | yes | Raw event lineage |

Never synthesize sequence/trade IDs. Corrections and cancels must be represented according to the source's documented semantics; do not silently mutate raw events.

## 3. Quote event schema

Required: source/dataset/instrument IDs, event and receive timestamps, sequence when provided, bid/ask prices, bid/ask sizes when supplied, quote condition, raw hash. Reject crossed/invalid quotes for classification; locked quotes and stale quotes are separately flagged. A top-of-book quote is not L2 depth.

## 4. L2 market-by-price event schema

Required when used: source/dataset/instrument IDs, event/receive timestamps, sequence, price level, side, operation (ADD/CHANGE/DELETE or documented source equivalent), displayed quantity, snapshot/delta marker, raw hash. Contract and tick metadata are mandatory. Book state is valid only after a valid snapshot and contiguous incremental updates. Unresolved sequence gaps invalidate state until documented recovery.

## 5. Derived feature schema

Every row includes `feature_id`, `definition_id`, `source_dataset_id`, `instrument_id`, `window_start_utc`, `window_end_utc`, `computed_at_utc`, `coverage_ratio`, `quality_state`, `input_event_count`, `input_range_start`, `input_range_end`, and lineage hashes.

Feature values may include buy/sell/unknown quantity, delta, CVD, print count, large-print quantity, price change in ticks, volatility-normalized progress, depth imbalance, and replenishment measurements. Units must be explicit. Unknown-side quantity is never silently assigned to BUY or SELL.

## 6. Detector event schema

Required fields: `event_id`, `event_type`, `instrument_id`, `contract_id`, `event_start_utc`, `event_end_utc`, `available_at_utc`, `detector_definition_id`, `dataset_id`, `quality_state`, `observations`, `supporting_evidence`, `contradictory_evidence`, `unknowns`, `reason_codes`, `input_lineage`, `code_revision`, `result_hash`.

`available_at_utc` is the earliest time all inputs needed to assert the candidate were available. A detector may not backdate availability to the beginning of its observation window.

## 7. Quality and fail-closed rules

- Missing required field: reject adapter input.
- Nonfinite price/size, nonpositive trade quantity, off-tick price, invalid contract metadata: reject event or mark dataset invalid according to scope.
- Duplicate event: deduplicate only with a source-defined stable identity and preserve duplicate audit; otherwise fail closed.
- Out-of-order or missing sequence: preserve raw record and mark affected interval invalid until recovery.
- Stale/missing quote: aggressor side UNKNOWN.
- Unknown aggressor side: excluded from signed delta; included in unknown quantity and coverage denominator.
- Invalid L2 book: no depth imbalance, replenishment, or book-based sweep detector output.
- Bar-only feed: no true trade delta/CVD or L2-derived detector output.

## 8. Current known data compatibility

The existing FTMO-Demo XAUUSD M1 dataset has OHLC, tick volume, real volume, and spread fields. It is suitable for price-context and existing market-structure research only. It does not satisfy this trade/quote/L2 contract. No Delta/CVD or institutional-footprint claims may be produced from it.
