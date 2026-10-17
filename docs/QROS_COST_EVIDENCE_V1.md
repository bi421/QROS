# QROS Cost Evidence Layer V1

Date: 2026-10-17. Research-only; no order execution.

## What is implemented

- `config/costs.yaml` declares MT5 symbol metadata from the retained manifest: `SYMBOL_POINT=0.01`, `digits=2`, `contract_size=100 XAU/lot`. Manifest SHA-256 is pinned and checked at load time.
- `researchos/orchestration/xauusd_cost_model.py` converts each bar's MT5 spread points to XAUUSD price units and calculates trade-level spread, commission, order-type slippage, gross return and modeled net return.
- Current `config/costs.yaml` schema v2 uses explicit adverse price-units-per-fill assumptions for market entry, TP limit, SL stop, and market exit. The earlier v1 0.05-ATR-per-side model is historical/superseded sensitivity only. Current commission remains USD 7 per lot round-turn assumed, and all slippage values remain unmeasured until backed by broker fill logs.
- Missing or invalid cost terms suppress net return. Assumed costs can never be reported as verified.
- `scripts/run_qros_bnf_cost_screen.py` creates a Parquet trade ledger using next-bar-open entry and close exit after 1, 3 or 5 bars. It records signal/entry/exit timestamps, entry/exit bar spread, ATR, gross return and cost components at 0.5x, 1x, 1.5x and 2x modeled costs.
- The script runs 1,000 random-entry and 1,000 shuffled-signal permutation repetitions for each timeframe and records p-values in a hashed trial registry; BH adjustment is applied to the eight registered p-values in this run.
- `FrozenXauusdM1Pipeline` now emits a separate costed-trade Parquet artifact for its SMA20/100 crossover events. It uses next-bar-open entry and the frozen one-day endpoint; this is separate from the BNF study.

## Unit conversion sanity check

The frozen MT5 manifest states point=0.01, digits=2, contract size=100 XAU per lot. Therefore:
- 9 points × $0.01 = $0.09 per XAU unit quoted spread.
- 19 points × $0.01 = $0.19 per XAU unit quoted spread.
- At a 100 XAU contract, those are approximately $9 and $19 per lot round-turn spread impact at that observed spread, before commission and slippage. Actual fill details can differ.

The earlier gross M15 mean of 0.0083% at a $2,500 reference price is about $0.2075 per XAU unit, or $20.75 for a 100 XAU lot before costs. This is an arithmetic illustration only; it is not directly interchangeable with the new next-bar-entry BNF trade ledger.

## Frozen-data cost sensitivity result

Source: `data/mt5/xauusd/XAUUSD_M1_2021_2025_MT5.csv`, SHA-256 `632950ee767eb8968a00331e6f8da35d3bc73e937bcb3ceb5c1b15f596939da9`. The data ends 2025-12-31.

The generated report is `artifacts/qros_bnf_cost_first_screen_20261017.json`; per-trade data is `artifacts/qros_bnf_costed_trades_20261017.parquet`.

At 1.5x the explicitly assumed cost model:
- M15: n=1,477; mean modeled net return = -0.02527%; `REJECTED_COST_FRAGILE`.
- H1: n=348; mean modeled net return = -0.02644%; `REJECTED_COST_FRAGILE`.
- H4: n=86; mean modeled net return = +0.02328%, but `INSUFFICIENT_SAMPLE` (minimum 100 for this screen).
- D1: n=8; mean modeled net return = -1.07144%, but `INSUFFICIENT_SAMPLE`.

These are cost-model sensitivity outcomes, not verified net results. M15/H1 are rejected under the declared assumptions, not under measured broker commission/slippage. H4 remains insufficient even though the 1.5x point mean is positive. D1 is unusably small.

The 8 registered permutation p-values have BH-adjusted values all above 0.05 (best adjusted q ≈ 0.0679). This family only covers the four timeframes and two controls registered in this artifact; it is not a complete registry of all historic QROS trials.

## Historical 19 FOLLOW-pair cost reassessment

The original engine's gross results were recomputed from `C:\Users\User\Documents\XAUUSDM15.csv` (211,868 rows, 2017-10-10 through 2026-10-14). **Verification passed for all 648 direction-specific candidates and 324 paired comparisons**: gross expectancy matched the original candidate artifacts within 1e-9 price units (maximum observed error 0.0); stored pair-difference consistency error was 1.11e-16.

Artifacts:
- Cost report: `artifacts/qros_follow_19_cost_reassessment_20261017.json` (SHA-256 `225fb1d481e63775a960925b27c0501814d81754f79f77fbe34ee3052e67ade3`).
- Historical trial registry: `artifacts/qros_historical_trial_registry_20261017.json` (SHA-256 `e200e28004f3db6b23fa7905de7c2b6b2cbe19011199e8f2f3e8a3c381f146b8`).
- Trade Parquet: `artifacts/qros_follow_19_costed_trade_rows_20261017.parquet`; 1,473,763 valid rows across both directions and all 19 pairs. It contains entry/exit times, bid and executable prices, exact observed M1 exit-minute timestamps, spread, ATR, gross/net returns, cost components, and 0.5x/1x/1.5x/2x sensitivity columns.
- Trade Parquet SHA-256: `7462c88c66f80452f601965f8f6fc7cc90f63ee92254eb590a5b4a074269e074`. The SHA manifest is `artifacts/qros_follow_19_costed_trade_rows_20261017.sha256`.
- M1-derived bars: 118,078; original M15 OHLC mismatches: **0**.
- Entry is the next M15 bar's first observed M1 open/spread. For TP/SL exits, spread is taken from the first M1 minute touching the original selected M15 barrier; timeout exits use the last M1 row in the exit bar. Long accounting uses entry ask / exit bid; short accounting uses entry bid / exit ask. Incomplete TP/SL M1 buckets are excluded rather than assigned a proxy spread: 783 FOLLOW and 668 REVERSE trades were excluded across the 19 pairs over the full re-evaluation interval.
- **Scope limit:** original M15 barrier prices and stop-first rule are preserved to keep gross outcomes comparable to the original engine. M1 identifies the exit spread timestamp; this is not a complete M1 bid/ask barrier replay.

### Cost decomposition (historical v1 ATR-slippage sensitivity; superseded)

The original v1 report includes spread-only net expectancy, spread-plus-commission net expectancy, ATR-slippage all-in expectancy, and break-even cost multipliers. For the current order-type slippage assumptions, use `artifacts/qros_follow_order_type_slippage_20261017.json` and its costed ledger instead.

Across the 19 FOLLOW variants on the final chronological 20% of the overlapping 2021–2025 interval:
- Spread-only net expectancy ranged from `-0.00334%` to `+0.00790%` per trade.
- Spread + commission ranged from `-0.00542%` to `+0.00582%`.
- Spread + commission + slippage at 1x was negative for all 19, ranging from `-0.02054%` to `-0.00936%`.
- At 1.5x all-in modeled costs, FOLLOW net expectancy ranged from `-0.03127%` to `-0.02008%`; all 19 were classified `REJECTED_COST_FRAGILE`. REVERSE expectancy was also negative across all 19.

Under the historical v1 ATR-slippage model, FOLLOW spread-only expectancy could be positive, while the ATR-scaled slippage assumption made all 19 selected variants negative. That sensitivity result is superseded by the order-type model below and is not broker-verified execution performance.

### Bootstrap and trial registry

- 1,000-replicate circular moving-block bootstrap; block length is the ceiling of the larger median realized FOLLOW/REVERSE holding period for each pair. Holding-period and overlap diagnostics are recorded per pair. Overlapping trades are common, so independent-trade standard errors are not used.
- Registry counts reconcile the historical numbers: 972 legacy full-grid candidate records; 648 original-engine direction-specific candidates; 324 paired comparisons. After deduplication, the absolute-edge FDR family contains 1,296 unique candidate hypotheses; the paired FOLLOW-vs-REVERSE family contains 324 hypotheses; the registry has 1,620 unique hypothesis records across those two distinct families.
- BH FDR at q=0.05 produced zero discoveries in the 1,296-candidate absolute-net-edge family and zero in either direction of the 324-pair comparison family. Eighteen of the 19 paired 95% intervals include zero; one unadjusted interval is positive, but its adjusted q-value is 0.4168 and it does not pass FDR. A positive paired difference would not establish positive absolute net expectancy in any case.

**Critical limitation:** the 19 pairs were selected from the original 2017–2026 full sample, which overlaps the 2021–2025 cost evaluation. This is not an untouched holdout. Commission ($7/lot round-turn) and the historical v1 ATR-slippage assumption were not broker-verified; the current v2 order-type assumptions are also unverified and are reported separately. `costs_verified=false`. No execution is authorized.

## Frozen pipeline integration run

A direct run of `FrozenXauusdM1Pipeline` on the frozen M1 CSV completed and emitted five artifacts, including a costed trade Parquet with 24,850 trade rows. The recorded artifact hashes and fail-closed decision are in `artifacts/qros_frozen_m1_costed_integration_20261017.json`. The gate returned `NO_TRADE_COST_PROVENANCE_INVALID` with `COSTS_NOT_VERIFIED`, as expected. Because `QROS_SOURCE_COMMIT` was unset, the audit record was marked `INVALID`; this is not a valid provenance certificate.

## Holdout and 2026 data

The BNF diagnostic over the frozen 2021-2025 dataset included 2025 in signal-threshold construction and performance summaries; 2025 must not be represented as an untouched holdout for that diagnostic.

Available local 2026 data found during the audit:
- `data/raw/histdata/xauusd/DAT_ASCII_XAUUSD_M1_202608.csv`: approximately 2026-08-02 through 2026-08-14, no spread column.
- `data/curated/xauusd/xauusd_h1_2026_recent_real.csv`: 2026-06-10 through 2026-08-20, with a volume field but no broker spread log.
- No complete Jan-Sep 2026 XAUUSD M1 series was found in these inspected locations. These fragments are not enough to certify all-timeframe out-of-sample costs.

## Fail-closed policy

- `cost_basis_declared` means all model fields are present and valid; it does not mean costs are measured.
- `costs_verified` remains false while commission/slippage are assumptions.
- The unified research gate requires `all_in_costs_verified=true`; modeled sensitivity cannot produce a candidate.
- Audit records with missing/non-SHA source commit are marked `INVALID`.
- `execution_authorized=false` in every emitted report and trade record.


## Follow-up: missing-data bias, order-type slippage, and frozen forward test (2026-10-17)

### Missing exit-spread rows

The gross-return outcomes for all 1,475,214 directional trade rows across the 19 selected pairs were reconstructed from the original M15 engine. 1,451 rows (0.09836%) were excluded from the costed ledger because the M1 exit bucket was incomplete; 1,473,763 rows remain. Gross outcomes are still observable for the excluded rows, so their return distribution can be compared without inventing spreads.

- FOLLOW: retained n=736,824, mean gross +0.000281%; excluded n=783, mean gross -0.060759%; excluded-minus-retained = -0.061040 percentage points; win rate 42.86% retained vs 23.75% excluded.
- REVERSE: retained n=736,939, mean gross -0.001891%; excluded n=668, mean gross +0.054970%; excluded-minus-retained = +0.056861 percentage points; win rate 42.11% retained vs 58.23% excluded.
- In the final chronological 20% of the overlapping period, FOLLOW excluded mean gross was -0.022620% (n=180) vs +0.004387% retained; REVERSE excluded mean gross was +0.012433% (n=195) vs -0.004490% retained.

This is material directional selection bias despite the small excluded fraction: removing these rows makes FOLLOW gross look better and REVERSE gross look worse. No independent-trade p-value is reported because trades overlap. Full data and pair-level diagnostics are in `artifacts/qros_follow_missing_data_bias_20261017.json`.

### Order-type slippage model

`config/costs.yaml` schema v2 replaces ATR-scaled slippage with explicit adverse price-units-per-fill parameters for `market_entry`, `tp_limit`, `sl_stop`, and `market_exit`. Current values (0.10, 0.01, 0.15, 0.10 XAU price units respectively) are **illustrative assumptions**, not observed execution data. The TP/SL/timeout reason selects the exit order class. The cost gate remains fail-closed and `costs_verified=false`.

The revised ledger sensitivity is in `artifacts/qros_follow_order_type_slippage_20261017.json` and `artifacts/qros_follow_19_order_type_costed_trades_20261017.parquet`. On the existing chronological holdout slice, order-type model net mean at 1x was -0.007503% per FOLLOW trade and -0.016468% per REVERSE trade; at 1.5x it was -0.013448% and -0.022457%, respectively. Break-even slippage allowances allocated to any one order class were negative for both directions (FOLLOW: market entry -$0.0542, TP limit -$0.1244, SL stop -$0.0965, market exit -$21.12; REVERSE: market entry -$0.3716, TP limit -$0.8935, SL stop -$0.6388, market exit -$150.51 per fill in XAUUSD price units). These negative allowances mean the aggregate already loses before positive slippage is added; they are not empirical estimates of observed fills. Results remain model-based, not broker-verified.

`scripts/import_mt5_fill_slippage.py` imports a broker/MT5 export with request-time bid/ask and deal fills, computes adverse slippage by symbol and order type, and emits hashed JSON/Parquet. It does not submit orders. At least 100 fills per order class are required for preliminary sample status; this threshold alone does not establish representativeness or verify costs. No demo fills were present locally, so no empirical slippage distribution is claimed.

### One-shot forward preregistration

`config/forward_validation_preregistration_20261017.json` freezes the current 19 pairs, code/config hashes, no-retuning rule, one evaluation, and a fixed source-time window from 2026-10-15 through 2027-01-15. It requires at least 100 exact-spread trades per direction/pair; otherwise the registered result is INCONCLUSIVE and the cutoff cannot be extended under this registration. The report status is `PREREGISTERED_WAITING_FOR_FORWARD_DATA`; no post-cutoff forward dataset is currently available in this repository. Do not inspect interim performance or change the rules.

### Cross-instrument status

`scripts/check_cross_instrument_readiness.py` records a fail-closed blocker for XAGUSD and EURUSD: neither instrument has the required local spread-bearing M1 dataset, symbol manifest, or symbol-specific cost config. The XAUUSD point/contract metadata cannot be reused. No cross-instrument performance comparison has been fabricated or reported. Supply broker-exported M1 OHLC+spread and exact instrument specs before running the frozen pipeline.

### Execution safety

No orders were submitted. `execution_authorized=false` remains enforced. Real demo fill collection requires a user-operated demo terminal and exported request-time quotes plus deal/fill records; it is an external dependency.
