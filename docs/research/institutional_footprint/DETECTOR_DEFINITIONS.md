# Institutional Footprint Engine — Detector Definitions

**Version:** `0.1.0` — draft. Thresholds are intentionally not selected from market outcomes.

## Common conventions

- All quantities retain native contract units; convert to lots/contracts only with manifest-defined multipliers.
- Use exchange timestamps and source sequence for event ordering. All intervals are half-open `[start, end)` unless a detector explicitly defines otherwise.
- Every threshold and window is part of an immutable detector definition and receives a deterministic SHA-256 `definition_id`.
- Reference distributions are computed only from data available before the event being scored, within the same registered instrument/session/contract regime where sample size permits.
- If the reference sample is inadequate, output `INSUFFICIENT_DATA`; do not fall back silently to a global threshold.
- The term “large participant footprint” means an observable statistical pattern, not proof of a single participant or institution.

## Detector catalogue

### D01 — Unusually large print

Inputs: valid trade events and contract metadata.

Measurements: trade quantity, historical percentile, median absolute deviation score, reference count, session/contract cohort, tick value equivalent where valid.

Candidate rule: quantity exceeds a preregistered cohort percentile and minimum reference sample. Exact percentile, sample minimum, and lookback are to be frozen in the Phase 1 definition grid before any real-data evaluation. Output one event per qualifying print or a documented aggregation, never both without distinct event types.

Counterevidence/limitations: block/cross/auction or special-condition trades; vendor aggregation; incomplete venue coverage; trade corrections; quantity units. Report flags and do not label the print “institutional.”

### D02 — Large-print cluster

Inputs: D01 candidates and complete-enough trade stream.

Measurements: print count, total size, signed/unknown size, inter-arrival times, cluster duration, share of observed feed volume.

Rule: fixed event-time window and minimum count/aggregate percentile, frozen before real data. Cluster membership is deterministic and non-overlapping or explicitly permits overlap; policy must be fixed.

### D03 — Aggressive flow cluster

Inputs: classified trade events plus valid synchronized quote context or exchange aggressor flags.

Measurements: buy/sell/unknown quantity, delta, classified coverage, print count, spread and quote age.

Rules: exchange-provided aggressor side and quote-inferred side remain separate feature streams. Quote test tie/locked/crossed/stale cases become UNKNOWN. No tick-rule fallback in V1 unless separately preregistered.

### D04 — Delta/CVD

`delta = buy_aggressor_quantity - sell_aggressor_quantity` for the declared window. CVD is a cumulative sum under one immutable reset convention. Unknown-side volume is reported separately. Report signed-volume coverage = classified quantity / total observed quantity. A low coverage interval cannot be interpreted directionally.

### D05 — Aggression/price response

Measure net aggressive quantity and price progress in ticks over preregistered event-time and trade-count horizons. Normalize price progress by a trailing, past-only volatility estimate and report raw ticks too. Candidate labels include `HIGH_AGGRESSION_HIGH_PROGRESS`, `HIGH_AGGRESSION_LOW_PROGRESS`, and `LOW_AGGRESSION_HIGH_PROGRESS`; these are descriptive states, not trade signals.

### D06 — Absorption candidate

BUY absorption candidate: unusually high BUY aggression with constrained upward price progress and persistence across the frozen horizon. SELL absorption is symmetric. A valid L2 replenishment observation can be additional support, not a mandatory assumption. Without L2, label `TRADE_PRICE_ABSORPTION_PATTERN`, not book replenishment. Output supporting and contradictory evidence, including whether price subsequently breaks through the contested level.

### D07 — Displayed-depth replenishment candidate

Requires valid reconstructed L2 market-by-price state. At a fixed price level and side, observe displayed depth depletion followed by renewed displayed quantity within a fixed event-time horizon, with contiguous sequence and no unresolved book invalidation. Report observed depth changes only. Do not call it iceberg or hidden institutional order detection.

### D08 — Liquidity sweep candidate

Requires a reference level created and available before the event (for example, a confirmed swing from the existing Market Structure Engine), actual trade-through evidence, and a preregistered post-trade response window. A wick-only bar pattern is not enough. The detector records the level source, trade-through quantity, time beyond level, and subsequent acceptance/rejection measurements.

## Cross-detector evidence policy

No single detector is sufficient to claim a “large participant.” A composite footprint may combine independent evidence classes (large executed size, repeated aggression, price impact/absorption, and valid displayed-depth response), but the composite definition and weighting must be preregistered. Avoid double-counting correlated features derived from the same prints. Report component events and missing components; do not compress them into an opaque confidence score.

## Strategy separation

No detector threshold may be optimized to maximize future trade P&L during engine development. A later follow-the-footprint strategy must have its own entry/exit rules, risk/cost model, multiple-testing family, and untouched prospective OOS. Detector event validity and strategy profitability are separate hypotheses.
