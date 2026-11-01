# Market Structure Variant Study — Specification and Pre-registration

**Preregistration:** `MSV1-DRAFT-2026-11-02`
**Status:** `BLOCKED — DRAFT ONLY; NOT AUTHORIZED FOR MARKET-DATA EXECUTION`
**Version:** 1.0.0
**Branch:** `feat/market-structure-variants`

> This document and `grid.json` freeze the proposed hypothesis family before any Market Structure variant has been run on market data. They are not an effective final pre-registration because the approved frozen dataset bytes, a fresh untouched holdout slice hash, and verified execution-cost evidence are not available in the current QROS workspace. Do not run Phase 2+ market-data work until these blockers are resolved and a new accepted pre-registration is committed.

## 1. Research question and scope

Test whether mechanically defined XAUUSD M1 swing/BOS/CHOCH events, with the fixed execution rules below, have repeatable positive net expectancy across chronological unseen data. The objective is to measure the full outcome dispersion across every registered definition, not to find or publish only the best variant.

The null/acceptable outcome is `NO_EDGE_FOUND` or `INSUFFICIENT_EVIDENCE`. No result from this study authorizes live trading, order routing, or profitability claims.

## 2. Dataset identity and holdout lock — BLOCKED

Proposed source identity reported in `artifacts/full_xauusd_evidence_audit_20261017.md`:

- Dataset: MT5 XAUUSD M1, 2021–2025.
- Reported rows: 1,764,176.
- Reported range: 2021-01-04 01:05 UTC through 2025-12-31 23:58 UTC.
- Reported full-dataset SHA-256: `632950ee767eb8968a00331e6f8da35d3bc73e937bcb3ceb5c1b15f596939da9`.
- Verification status in this work session: `UNVERIFIED — dataset bytes are not present in QROS/data/mt5/xauusd and no configured DVC remote is available`.

The audit's reported SHA is recorded as provenance only; it is not claimed as re-hashed or verified here. Proposed chronological OOS boundary for planning is `2025-01-01T00:00:00Z` through `2025-12-31T23:59:59Z`, within the reported full-dataset SHA above. The independent SHA-256 of that slice is unavailable because the dataset bytes are absent. The 2025 period has also appeared as a holdout in unrelated prior XAUUSD audits, so it cannot honestly be called a globally untouched holdout for a new study. No fresh post-2025 M1 holdout with at least 1,245 eligible observations is available in the current workspace.

Required before this pre-registration can become effective:

1. Retrieve an already-approved immutable dataset version through its documented source-of-truth boundary; do not rebuild, repair, or silently substitute data.
2. Verify exact source bytes, SHA-256, timestamp range, row count, timezone, schema, duplicate/gap counts, and source manifest.
3. Identify a genuinely unused chronological OOS holdout slice, record its exact UTC boundaries and its independently computed slice SHA-256 here and in the run manifest.
4. Ensure the holdout is not read for feature selection, parameter choice, threshold choice, or debugging. It may be consumed exactly once after every development gate passes.

The proposed 2025 boundary above is recorded for provenance only, not accepted as an untouched holdout. The full dataset SHA is source-reported; the 2025 slice SHA is `UNAVAILABLE`. Existing reports' date boundaries are not silently reclassified as a fresh holdout.

## 3. Timeframe, timestamps, gaps, and sessions

- Primary and only tested timeframe: XAUUSD M1.
- No higher-timeframe resampling or multi-timeframe filter is included in V1. This avoids adding an unregistered resampling/confirmation rule.
- Timestamps must be timezone-aware UTC, unique, strictly increasing, and mapped to completed one-minute bars. Reject duplicate, out-of-order, invalid-OHLC, or timezone-ambiguous input; do not sort/repair it silently.
- No synthetic bars are inserted. A gap is any adjacent timestamp difference other than exactly 60 seconds.
- Swing windows may not bridge a gap. A candidate pivot whose left/right confirmation window crosses a gap is ineligible.
- Multi-bar break confirmation must consist of consecutive actual M1 bars; reset the confirmation streak at every gap. Confirmed swing levels and trend state persist across a gap, but a gap alone is not a break. A first post-gap bar can confirm a one-bar break only if its completed observation is beyond the level; fill remains at the next actual contiguous bar open. If no next contiguous bar exists, skip the trade and record the reason.
- Session labels are descriptive UTC buckets only: `[00:00,07:00)`, `[07:00,13:00)`, `[13:00,21:00)`, `[21:00,24:00)`. They are not exchange-session assertions and are not DST-adjusted. No session filter is used in V1.
- Weekend/holiday gaps are treated by the same gap rules; no fabricated candles or inferred intrabar path.

## 4. Exact structure definitions

For integer `n = swing_window`, a swing high at bar `i` exists only if `High[i]` is strictly greater than every `High[i-n:i]` and every `High[i+1:i+n+1]`. It is not known until bar `i+n` has closed. A swing low is symmetric using strict `<` on Low. Equal highs/lows are not pivots; no tolerance or clustering is applied.

- The pivot timestamp/index is `i`; its availability/confirmation timestamp/index is `i+n`.
- A pivot is not available to any decision before its confirmation bar closes.
- Only the most recently confirmed swing high and swing low are active levels.
- A level can produce at most one break event; it is consumed after a confirmed break and becomes eligible again only when replaced by a newer confirmed pivot.
- `wick` break basis: bullish observation uses High; bearish observation uses Low.
- `close` break basis: both directions use Close.
- A bullish break requires every bar in the registered confirmation window to be strictly above `level + buffer`; a bearish break requires every bar to be strictly below `level - buffer`.
- `buffer = break_buffer_atr × ATR14`, calculated independently at each confirmation bar from current and past data only. ATR14 for V1 is the simple rolling mean of true range over 14 completed bars (not Wilder smoothing). No future bar may enter ATR.
- A first directional break while structure state is neutral is `BOS`. A break in the same direction as the current state is `BOS`. A break opposite the current state is `CHOCH`, then state flips to the new direction.
- If a single OHLC bar crosses both active swing levels on a wick basis, intrabar ordering is unknowable. Mark it `AMBIGUOUS`, consume neither direction as a valid trade signal, and do not advance trend state on that bar.
- `break_index` is the bar on which the full confirmation rule becomes known, never the original pivot bar.

## 5. Registered parameter grid

`grid.json` contains all definitions explicitly. It is a QROS-defined screening family, not a claim to reproduce Ironclad's private or exact grid.

| Axis | Values | Count |
|---|---|---:|
| Symmetric swing window `n` | 2, 3, 4, 5, 6, 8, 10 | 7 |
| Break basis | wick, close | 2 |
| Consecutive confirmation bars | 1, 2 | 2 |
| Break buffer | 0.00, 0.05 × ATR14 | 2 |
| CHOCH convention | opposite confirmed swing break | 1 (fixed) |
| Trend filter | off | 1 (fixed) |
| **Total registered variants N** | `7 × 2 × 2 × 2 × 1 × 1` | **56** |

No parameter may be added, removed, or edited after the first variant result is computed. A later change requires a new pre-registration version and increases the total multiple-testing family to include every earlier attempted definition.

`grid.json` SHA-256: `e09001e1602cf5624e72ea35ab6c37a43db6a5fa3aa487705073cad81603726a`

Reproduction command:

```powershell
Get-FileHash docs/research/market_structure/grid.json -Algorithm SHA256
```

## 6. Signal, entry, stop, target, and portfolio rules

- Only a fully confirmed BOS or CHOCH event can create a signal. One event can create at most one signal.
- Signal decision time is the close of `break_index`.
- Fill is at the next actual contiguous M1 bar open. Never fill on the signal bar close. If the next row is separated by a gap, skip the signal.
- Long stop anchor: the most recently confirmed active swing low available at signal time. Short stop anchor: the most recently confirmed active swing high available at signal time. The anchor and its confirmation index must be stored in the event/signal record.
- If the opposite swing anchor does not exist, is not confirmed before the signal, or yields a non-positive risk distance after the next-open fill, do not trade; record `NO_VALID_STOP_ANCHOR`.
- Stop is fixed at that opposite confirmed swing price; it is not moved after entry. No discretionary trailing stop or break-even adjustment.
- Initial risk `R` is the absolute entry-to-stop price distance. Fixed unit risk is 1R per trade. No position-size optimization, compounding, leverage optimization, or risk recovery sizing.
- Take profit is exactly 2R from entry. No target optimization.
- Maximum holding period is 60 completed M1 bars after entry; if neither barrier is hit, exit at the close of the 60th bar.
- Only one open position at a time. Signals occurring while a position is open are recorded as ignored due to `POSITION_OPEN`; no stacking, hedging, or pyramiding.
- At dataset/fold boundary, any open position is closed at the last available close before the boundary, with applicable costs, and marked `BOUNDARY_EXIT`.
- Intrabar stop/target ambiguity: if both are touched within the same OHLC bar, stop wins. If a bar opens through the stop, fill at the worse open. If a bar opens beyond the target, fill at the target price (no favorable price improvement).
- If the entry bar itself touches stop or target, the same conservative barrier rule applies after the next-open fill.

## 7. Cost model — BLOCKED / UNVERIFIED

A prior audit records a `0.36` XAUUSD price-unit round-trip spread scenario derived from 36 reported points × 0.01 point size. That audit explicitly says this is not a verified historical average and excludes slippage and commission. Therefore it is only a sensitivity reference, not an approved execution-cost model.

- Spread reference scenario: 0.36 price units round-trip, `UNVERIFIED`.
- Commission: `UNVERIFIED / NOT AVAILABLE`; no zero-cost assumption is permitted.
- Slippage: `UNVERIFIED / NOT AVAILABLE`; no zero-cost assumption is permitted.
- Stress multipliers for the spread component: ×1.0, ×1.5, ×2.0.
- Commission and slippage must be added from broker/account evidence before any net-edge claim. Cost values must be in the same XAUUSD price units as the OHLC series and converted from contract/lot units using verified contract metadata.
- `config/costs.yaml` remains unchanged and `UNVERIFIED`. No code may set `cost_model_verified=true` based on this draft.
- Missing/unverified cost inputs force `NO_TRADE_COST_AUDIT_UNVERIFIED`; gross results may be diagnostic only and cannot yield `CANDIDATE`.

## 8. Metrics and sample gate

Report every variant, including failures and insufficient variants:

- eligible observations after warm-up and gap exclusions;
- trade count and skipped-signal counts by reason;
- net expectancy per trade in R, with gross and each cost scenario separately;
- profit factor from net R wins/losses;
- maximum peak-to-trough drawdown in R;
- daily-equity Sharpe, annualized with `periods_per_year = 252` daily observations;
- 95% block-bootstrap confidence interval for mean net R/trade;
- per-variant deterministic `definition_id`, `run_hash`, `result_hash`, dataset SHA, cost-evidence SHA, and full configuration.

Minimum eligible observations per variant: **1,245**. A variant below 1,245 is `INSUFFICIENT`, excluded from ranking and candidate promotion, but remains in the all-variants output. The 1,245 gate is not a trade-count target and must never be lowered. No additional arbitrary minimum trade count is introduced in this draft; uncertainty and dependence diagnostics must be reported explicitly.

## 9. Chronological development, walk-forward, and locked OOS

The exact date boundaries and slice hashes cannot be frozen until the approved dataset bytes are recovered and verified. The only source-reported 2021–2025 dataset identity is recorded in Section 2; it is not accepted as verified evidence here. The reported 2025 holdout was already used in unrelated prior XAUUSD audits, so it is not a fresh global holdout.

Before any variant execution, a valid pre-registration must replace this section with:

1. Exact development start/end UTC and slice SHA-256.
2. Every walk-forward train/test window, purge/embargo length, and per-window slice SHA-256.
3. A genuinely unused locked OOS start/end UTC and independently verified slice SHA-256.
4. A one-use OOS lock record and consumed-state evidence mechanism.

No market-data result may be computed until these values are recorded and committed. No final holdout may be used for feature engineering, parameter selection, debugging, or repeated testing.

## 10. Statistical validation and decision thresholds

- Test family size is `N=56` for V1. All attempted definitions, including failures and insufficient variants, remain in the family ledger.
- Per-variant one-sided null: expected net R/trade is not greater than zero. Use a predeclared moving-block bootstrap with 10,000 resamples, block length 60 trades, and fixed RNG seed `20261102`. Report raw p-values and 95% intervals.
- Apply Holm–Bonferroni across all 56 registered variants at family-wise alpha `0.05`. Do not substitute unadjusted p-values.
- Compute Deflated Sharpe Ratio using the full trial count `N=56`; threshold `DSR ≥ 0.95` for candidate eligibility.
- Walk-forward: every predeclared test fold must have positive net expectancy after verified costs; report all fold results, including negative folds.
- Parameter-neighborhood stability: a variant may pass only if at least 75% of its directly adjacent registered variants (one axis step away, all other axes identical) have positive net expectancy in aggregate walk-forward validation. Missing/insufficient neighbors count as not passing.
- Regime robustness: report all UTC session buckets and volatility terciles; no regime may be omitted. Regime splits are descriptive gates; no post-hoc regime filter may be added to the strategy.
- Cost stress: the surviving variant must retain positive net expectancy at ×1.0, ×1.5, and ×2.0 spread, with verified commission and slippage included at every level.
- Locked OOS: only variants that pass every development/walk-forward, multiplicity, DSR, neighborhood, regime-reporting, and cost-stress gate may be run. Run each survivor exactly once on the locked OOS. No threshold or rule changes after OOS consumption.

Decision enum:

- `INSUFFICIENT_EVIDENCE`: approved data, cost evidence, sample size, or statistical precision is inadequate; includes all blocked/insufficient runs.
- `NO_EDGE_FOUND`: the registered study completed valid development, validation, and locked OOS gates but no variant passed all criteria.
- `CANDIDATE`: at least one variant passes Holm–Bonferroni, DSR, every walk-forward fold, neighborhood stability, verified cost stress, and the one-use locked OOS with positive net expectancy and 95% block-bootstrap CI entirely above zero. `CANDIDATE` is research evidence only, not a live-trading recommendation or guarantee.

No result may be called profitable or robust solely because its in-sample equity curve is positive.

## 11. Reproducibility, artifacts, and phase gates

- Same dataset bytes + same definition + same execution/cost config + same code version must produce identical `result_hash`.
- Every variant must end in exactly one recorded state: success, failure, or insufficient. No silent drops.
- Preserve all 56 variants in reports; show best, median, worst and full distribution. Never publish only winners.
- Every cited artifact must be committed or stored in an explicitly documented immutable artifact store, with SHA-256 and lineage.
- No live trading, order sending, live MT5, queues, Auth/RLS changes, Phase 5.2 changes, or new backtest engine.
- Phase 2 may begin only after this pre-registration is made effective with verified dataset/holdout hashes and verified cost evidence. Phase 3+ must not compute Market Structure results before the effective SPEC and grid are committed.

## 12. Current blockers and decision

1. Approved frozen XAUUSD M1 dataset bytes are absent from the QROS workspace; DVC is not configured/installed in this environment.
2. A fresh untouched OOS holdout slice and its SHA-256 cannot be verified from the available files.
3. Spread scenario 0.36 is explicitly unverified; commission and slippage evidence are missing.
4. `config/costs.yaml` remains `UNVERIFIED` with null values.

**Phase 1 decision: BLOCKED.** `SPEC.md` and `grid.json` are a versioned draft only. No market-data variant result has been computed. Do not label this draft as an accepted pre-registration or proceed to Phase 2 until the blockers are resolved and the effective pre-registration is committed.
