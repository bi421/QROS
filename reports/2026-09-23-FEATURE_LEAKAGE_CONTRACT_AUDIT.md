# Phase 5.2 Rebuild — Feature / Leakage Contract Audit

## Status

**CONTRACT DEFINED — MODEL EXECUTION BLOCKED UNTIL LOCAL TESTS PASS AND FINAL SAMPLE GATE IS VERIFIED**

## Verified repository facts

1. The rebuild daily dataset is built from raw XAUUSD M1 candles aggregated by UTC calendar day. Macro values are joined only on exact common UTC calendar days; no interpolation or forward-fill is performed.
2. The canonical real-data run produced **1246** exact four-way common rows for 2021-01-04 through 2025-12-30.
3. The existing ResearchOS price `FeatureBuilder` exposes **19** features. Its longest finite warm-up dependency is the 60-observation `vol_regime` path (`historical_volatility(..., 60)`).
4. The existing Phase 5.2 macro builder defines three deterministic features per macro factor: `return_1`, `roll_mean_return_5`, and `roll_zscore_20`.
5. The existing forward-return label contract is `close[t+h] / close[t] - 1`; the final `h` rows are undefined for a positive horizon.

## Timing decision

The rebuild uses an explicit end-of-day decision convention:

- Feature row `t` represents information known after UTC day `t` has completed.
- Prediction timestamp is `t+1 00:00:00Z`.
- Same-day DXY, US10Y, and VIX daily observations are therefore permitted as features under this convention.
- No feature may depend on observations from `t+1` or later.
- The future-return label may depend on future prices because it is a supervised target, not an input feature.

This timing convention must remain explicit in the generated dataset metadata. If the intended decision time changes, macro lagging must be re-audited rather than silently changed.

## Label decision

Default Phase 5.2 rebuild horizon is **5 common daily observations** with threshold `0.0` and multiclass labels:

- `1`: future return > 0
- `0`: future return = 0 under threshold 0
- `-1`: future return < 0

The label at day `t` uses `close[t+5]`. Therefore the last five common observations cannot be labeled.

## Sample accounting

Starting from the verified 1246 common daily rows:

`1246 common rows - 60 feature warm-up rows - 5 label-tail rows = 1181 final usable rows`

The Phase 5.2 experiment gate remains:

`1000 train + 200 validation = 1200 minimum usable rows`

Therefore the current construction is **19 rows short** of the minimum gate. This is a genuine scientific blocker. The rebuild must not lower the gate or manufacture rows to bypass it.

## Implemented rebuild contract

`researchos/experiments/phase52_rebuild/feature_contract.py` records:

- the 19 frozen price feature names;
- the three macro features per factor;
- the five isolated feature-set variants;
- horizon = 5;
- threshold = 0;
- warm-up = 60;
- train = 1000;
- validation = 200;
- explicit after-day-close timing;
- final sample accounting rule.

`feature_dataset.py` constructs isolated `PRICE_ONLY`, `PRICE_DXY`, `PRICE_US10Y`, `PRICE_VIX`, and `PRICE_ALL` matrices without changing the underlying estimator.

## Required verification before model execution

1. Run the rebuild feature tests locally.
2. Run the complete Phase 5.2 rebuild test set.
3. Execute the feature builder on the real 1246-row daily dataset.
4. Confirm each feature-set final count is exactly 1181.
5. Confirm the 1200 gate blocks execution deterministically.
6. Only after a scientifically justified data-construction change raises usable rows to >=1200 may model/evidence execution begin.
