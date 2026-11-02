# Market Structure Variant Study — Specification and Pre-registration

**Preregistration:** `MSV1-DRAFT-2026-11-02`
**Status:** `DRAFT — DATASET AUDITED; MARKET-DATA EXECUTION BLOCKED PENDING COST AND FUTURE-OOS GATES`
**Version:** 1.0.0
**Branch:** `feat/market-structure-variants`

> The 56-definition family is frozen in `grid.json`; no Market Structure variant has been run on market data. A new FTMO-Demo XAUUSD M1 dataset is now locally acquired and independently audited. This remains a draft for market-data execution: historical development data has prior research exposure, the prospective OOS is future data whose hash cannot exist yet, and the account-specific volume-band/slippage cost model is not certified. Phase 2/3 structural code and synthetic tests may proceed; do not run the variant grid on market data until the cost model and OOS lock gates are accepted.

## 1. Research question and scope

Test whether mechanically defined XAUUSD M1 swing/BOS/CHOCH events, with the fixed execution rules below, have repeatable positive net expectancy across chronological unseen data. The objective is to measure the full outcome dispersion across every registered definition, not to find or publish only the best variant.

The null/acceptable outcome is `NO_EDGE_FOUND` or `INSUFFICIENT_EVIDENCE`. No result from this study authorizes live trading, order routing, or profitability claims.

## 2. Dataset identity and holdout lock — DATASET PASS / CONFIRMATORY RUN BLOCKED

### Acquired dataset identity

- Dataset ID: `FTMO_DEMO_XAUUSD_M1_2021_2026_V1`.
- Source: MetaTrader 5 history from server `FTMO-Demo` (company reported by terminal: `FTMO Global Markets Ltd`). This is an FTMO simulated-trading data feed, not exchange-consolidated gold data.
- Symbol/timeframe: `XAUUSD` / `M1`.
- Terminal build: `6292`; terminal `maxbars`: `5,000,000`.
- Symbol metadata: digits `2`; point/tick size `0.01`; contract size `100`.
- Requested UTC range: `2021-01-01T00:00:00Z` through `2026-10-31T23:59:59Z`.
- Actual first/last bars: `2021-01-01T00:00:00Z` through `2026-10-30T23:49:00Z`.
- Rows: `2,046,268` across `70` monthly CSV files.
- Concatenated monthly CSV bytes SHA-256: `e63acae2c39ff2b14538c1a3e696aa9e90da59274e4ca6184c1542dc5b812c06`.
- Inventory SHA-256: `44c9ceef74bad2a40ffb50ea246f10bbf4e3cc3455b6f4f4698c81f1b3a8fb11`.
- `manifest.json` SHA-256: `f756e2721f5d272c3dd09a60f69f37887ffc653d20aff35c11c64336912810bf`.
- `source_context.json` SHA-256: `8115cdc76e400da5027f72bc357ec66cea0014aa9aa177630e76913677eca060`.
- `independent_audit.json` SHA-256: `63c31451806d510e8eb01902a9df39609e7de70727117cb14c8491da7edbd389`.

The old audit's reported 1,764,176-row 2021–2025 dataset and SHA `632950ee767eb8968a00331e6f8da35d3bc73e937bcb3ceb5c1b15f596939da9` remain unverified and are not this dataset. Do not merge, alias, or claim equivalence between them.

### Integrity audit

`py -3 scripts/audit_mt5_monthly_dataset.py data/raw/mt5/ftmo_demo_xauusd_2021_2026` returned `INTEGRITY_PASS=True`:

- `2,046,268` rows; `70/70` manifest chunks and monthly files verified; all per-file SHA-256 and row counts matched.
- Timestamp parse failures `0`; out-of-range rows `0`; duplicate timestamps `0`; non-increasing intervals `0`.
- Invalid OHLC rows `0`; negative tick-volume, real-volume, or spread rows `0`.
- Gaps greater than 60 seconds: `1,917` (368 of 60–300s; 28 of 301–900s; 1,213 of 901–21,600s; 308 above 21,600s; maximum `263,760s`). These are observed timestamp gaps, not automatically classified as data loss. No synthetic bars were inserted.
- The audit is structural validation of this FTMO feed; it does not establish that the feed is globally representative, that every gap is explained, or that recorded spread equals an executable fill for every order size.

### Pre-registered data partitions

- Development data: `2021-01-01T00:00:00Z` through `2025-12-31T23:59:59Z`; `1,753,910` rows; concatenated monthly CSV bytes SHA-256 `e2e754cabf133436f91b0592aaf7b9a1d9161037171355ffcb0357f2fe77a507`. This period has prior QROS XAUUSD research exposure and is development-only, not a fresh confirmatory holdout.
- Walk-forward folds and raw slice hashes are fixed in Section 9. The final 60 observed M1 bars of each training interval are purged because the registered maximum holding period is 60 bars.
- Exploratory 2026 data: `2026-01-01T00:00:00Z` through `2026-10-31T23:59:59Z`; `292,358` rows; SHA-256 `f5bc8c6aca03a3e6c0ab7c21e68bddb4f493074e6423e0feb0b3842ec7feccd0`. This is diagnostic only, not confirmatory OOS: the repository's prior evidence audit already evaluated XAUUSD M15 through `2026-10-14`, and a later M15 sample was also inspected.
- Prospective study-locked OOS: `2026-11-02T00:00:00Z` through `2027-04-30T23:59:59Z`. This is future data and is not yet present; its SHA-256 must be recorded after the window closes and before the one-use OOS run. No data from this interval may be used for development, debugging, or parameter selection.

### Storage and provenance limitation

The raw data and audit JSON are local under `data/raw/mt5/ftmo_demo_xauusd_2021_2026/` and are ignored by Git. No DVC remote is configured, and the QROS Staging `qros-datasets` Supabase bucket contained zero objects at inspection. The dataset therefore has verified local hashes but is not yet backed by an immutable remote artifact store. Preserve this directory and do not overwrite it; any reacquisition must use a new versioned directory.

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

## 7. Cost model — DOCUMENTED PARTS / NOT CERTIFIED

### Historical spread field

- MT5 `MqlRates` records a `spread` field; MetaTrader 5 Market Watch documentation defines spread in points. This dataset's symbol point is `0.01`, so one recorded spread point corresponds to `0.01` XAUUSD price units.
- Observed spread-point quantiles: median `15` points (`0.15` price units); 95th percentile `47` points (`0.47`); maximum `1,718` points (`17.18`).
- Zero-spread rows: `34,022`; rows above 100 points: `1,318`; rows above 500 points: `12`.
- Do not silently treat zero spread as free execution, clip wide-spread observations, or assume this bar field is the exact executable bid/ask at entry and exit. Retain all rows and mark zero/missing or extreme observations explicitly in cost diagnostics.

### Commission and volume bands

- FTMO's 25 Sep 2025 update states Metals CFD commission changed from `0.0005%` to `0.0007%` of volume per side, effective from market open on 29 Sep 2025.
- FTMO's 16 Apr 2026 update states volume-band execution was extended to all active FTMO Accounts, Challenges, Verifications, and Free Trials from 20 Apr 2026. Execution price therefore depends on trade size.
- These are published firm-level conditions, not yet independently reconciled to the exact XAUUSD volume-band tiers and realized commission for this terminal/account. Status: `DOCUMENTED_NOT_ACCOUNT_VERIFIED`. Do not convert them into a fixed per-lot commission without applying the correct notional, contract size, effective date, and volume band.

### Slippage and certification

- Slippage remains `UNVERIFIED`; OHLC bars alone do not reveal the actual fill slippage. FTMO's trading updates explicitly warn of slippage, spread widening, reduced liquidity, and abnormal price behaviour.
- `config/costs.yaml` remains unchanged and `UNVERIFIED`. No code may set `cost_model_verified=true` from published commission terms or a historical bar spread field alone.
- Until the exact XAUUSD volume-band schedule, account-specific commission, and defensible slippage model are evidenced, the engine must return `NO_TRADE_COST_AUDIT_UNVERIFIED`. Gross/spread-only outputs, if later authorized, are diagnostic only and cannot yield `CANDIDATE`.

References: [MQL5 `MqlRates`](https://www.mql5.com/en/docs/constants/structures/mqlrates); [MetaTrader 5 Market Watch](https://www.metatrader5.com/en/terminal/help/trading/market_watch); [FTMO Trading Update 25 Sep 2025](https://ftmo.com/en/blog/trading-updates/trading-update-25-sep-2025/); [FTMO Trading Update 16 Apr 2026](https://ftmo.com/en/blog/trading-updates/trading-update-16-apr-2026/).

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

### Frozen historical partitions

All hashes below are SHA-256 over the raw monthly CSV file bytes concatenated in chronological filename order. They are tied to dataset ID `FTMO_DEMO_XAUUSD_M1_2021_2026_V1` and the manifest/inventory hashes in Section 2.

| Fold | Training window | Training rows (pre-purge) | Training raw-slice SHA-256 | Test window | Test rows | Test raw-slice SHA-256 |
|---|---|---:|---|---|---:|---|
| WF1 | 2021-01-01 to 2022-12-31 UTC | 701,610 | `bba15543e4014c1dd597c01fabee1fab73601348d0ff3be968510a56a597806f` | 2023-01-01 to 2023-12-31 UTC | 349,508 | `cb230bc1abdb40e4fe78e9f7cceee88f3d25427e7387540e162348ead44a1e2c` |
| WF2 | 2021-01-01 to 2023-12-31 UTC | 1,051,118 | `375ce865cdf19c2e50d321db7997280d2e1270fea0be5abb7d0c90a43d20d56a` | 2024-01-01 to 2024-12-31 UTC | 352,105 | `d0172a580884c8f46534adc1c9afa0c5fdb112e3fdcdae5f9e46cf141f97efa0` |
| WF3 | 2021-01-01 to 2024-12-31 UTC | 1,403,223 | `59ad5fad9601053e0baa308e63708975f23e821a4d4ea39c18ca09a25aed415f` | 2025-01-01 to 2025-12-31 UTC | 350,687 | `278343c931906e5bec0f1e790cbecf5668f01bdaf3f801e64f92013a6fcf3fd2` |

Purge the final `60` observed M1 bars from each training interval before the next test boundary; this matches the registered 60-bar maximum holding period. Test intervals are chronological and disjoint. No bars are synthesized to bridge gaps. The 2021–2025 development period has prior QROS research exposure; these folds are research-development validation, not independent confirmation against all prior strategy searches.

### Exploratory and prospective holdout

- 2026-01-01 through 2026-10-31 UTC is an exploratory diagnostic slice only (`292,358` rows; raw-slice SHA-256 `f5bc8c6aca03a3e6c0ab7c21e68bddb4f493074e6423e0feb0b3842ec7feccd0`). Prior M15 evaluation over this period means it is not accepted as fresh confirmatory OOS. Do not use it to choose among the 56 variants.
- Prospective study-locked OOS boundary is fixed now at `2026-11-02T00:00:00Z` through `2027-04-30T23:59:59Z`. Its bytes/hash do not yet exist. After the interval closes, acquire from the same named FTMO-Demo source, validate schema/gaps/cost provenance, record the exact slice SHA-256, and lock the artifact before the one-use test.
- No future OOS data may be used for feature engineering, parameter selection, debugging, or repeated testing. If the source server, symbol contract, or data schema changes, stop and register a new dataset version rather than silently appending it.

The 1,245-observation minimum remains mandatory per variant after warm-up and gap exclusions. No market-data variant run is authorized until the cost gates in Section 7 are resolved and this SPEC/grid commit is frozen.

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
- Phase 2 immutable-definition work and Phase 3 detector work may proceed using synthetic fixtures only. Phase 4+ adapters may be implemented but must not consume market data; Phase 5 grid execution and all variant results remain blocked until Section 7 cost evidence is accepted and the prospective OOS lock is available.

## 12. Current blockers and decision

1. Dataset acquisition and local byte-integrity audit: `PASS`. Remote immutable storage/backup is still absent (no DVC remote; Supabase `qros-datasets` bucket empty).
2. Development and walk-forward partitions: frozen with raw-slice hashes; prior research exposure means they are not independent confirmation against all historical strategy searches.
3. 2026 data: exploratory only; prior M15 research exposure prevents its use as fresh confirmatory OOS.
4. Prospective locked OOS: boundaries fixed at 2026-11-02 through 2027-04-30 UTC; data and slice hash are necessarily pending until the period closes.
5. Historical spread field is available and structurally audited, but zero values, extreme values, and volume-band execution require explicit handling.
6. FTMO commission terms are documented, but exact account-specific XAUUSD volume-band tiers and realized commission are not independently verified; slippage evidence is missing.
7. `config/costs.yaml` remains `UNVERIFIED` with null values.

**Phase 1 decision: DRAFT ACCEPTED FOR STRUCTURAL IMPLEMENTATION; MARKET-DATA EXECUTION BLOCKED.** The dataset and split identities are recorded, but no Market Structure variant has been run on market data. Phase 2/3 may proceed with synthetic tests only. Do not compute market-data variant results or claim a candidate until the cost model is evidenced and the prospective OOS window is locked with a verified hash.
