# QROS — XAUUSD Full Evidence Audit
**Run date:** 2026-10-17
**Purpose:** Determine whether existing XAUUSD research signals show repeatable predictive value or positive net expectancy.
**Execution:** Offline research only. No orders placed. No source code, data files, commits, or pushes changed by this audit.

## Executive verdict
**NO VERIFIED TRADING EDGE. DO NOT ENABLE LIVE TRADING FROM THESE RESULTS.**

The strongest direct cost-aware test is negative: the frozen M15 candle-velocity impulse strategy had negative gross expectancy on the 2026-01-01 through 2026-10-14 evaluation period, before costs. The 2021–2025 2025 holdout was positive gross on average but did not cover a 0.36 XAUUSD-price-unit round-trip cost assumption. Directional first-touch tests were close to 50/50 and not statistically significant. The M1/H1 moving-block-bootstrap directional-value tests failed to reject zero signed return. A short H4 sample looked positive, but 98% of holdout states were UP, so this largely measures upward market drift rather than demonstrated state-selection skill.

## Data used
1. **MT5 XAUUSD M1, 2021–2025:** 1,764,176 rows; 2021-01-04 01:05 UTC through 2025-12-31 23:58 UTC. Manifest reports 0 duplicate timestamps, 0 invalid OHLC rows, 1,577 gaps over one minute. SHA-256: `632950ee767eb8968a00331e6f8da35d3bc73e937bcb3ceb5c1b15f596939da9`.
2. **MT5 XAUUSD M1 context, 2020:** 351,258 rows; 2020-01-02 through 2020-12-31.
3. **XAUUSD M15 CSV:** 211,868 rows; 2017-10-10 01:00 through 2026-10-14 06:15; SHA-256: `bc574cba7eedca456333ee736adf81639f379ed58213e18e076b9b7003783e0b`. There were 2,355 M15 gaps. The main 2021–2025 audit window contained 118,078 bars. Timestamp timezone is unverified.
4. **XAUUSD H1, 2021–2025:** 28,796 rows.
5. **XAUUSD H1 recent, 2026:** 1,145 rows, 2026-06-10 through 2026-08-20.
6. **XAUUSD H4 sample:** 1,800 rows, 2023-06-01 through 2024-03-26; this is a limited sample, not a full multi-year H4 test.
7. **XAUUSD D1:** 1,290 rows, 2021-01-04 through 2025-12-31; a separate close-only daily dataset contains 1,466 rows through 2026-09-07.
8. **Macro data ledger:** canonical alignment of XAUUSD, DXY, US10Y, and VIX produced 1,246 common daily rows, 1,186 after feature warm-up and 1,181 after a five-row label horizon. The existing phase52 experiment gate is BLOCKED/NOT READY.

These are primary/canonical datasets and distinct timeframe/context samples, not every duplicate, monthly chunk, export, and derived copy on disk. Duplicate source variants were not blindly pooled because that would double-count observations.

## Direct strategy test: M15 candle-velocity impulse
Signal: completed M15 candle-velocity impulse; entry at the next contiguous M15 open; exit at the close after 3 or 5 M15 bars. No TP/SL. P&L units are XAUUSD price units per ounce-equivalent. A 0.36 round-trip cost was applied as an explicit scenario based on the MT5 manifest's reported spread field (36 points × 0.01 point size). This is not a verified historical average spread and excludes slippage/commission, so it is not a complete cost model.

| Period / horizon | Trades | Gross expectancy | Win rate | Net after 0.36 assumption |
|---|---:|---:|---:|---:|
| 2021–2024, 3 bars | 5,946 | +0.0084 | 47.98% | -0.3516 |
| 2025 holdout, 3 bars | 1,264 | +0.1194 | 48.18% | -0.2406 |
| 2021–2024, 5 bars | 5,932 | +0.0931 | 49.01% | -0.2669 |
| 2025 holdout, 5 bars | 1,256 | +0.1664 | 48.01% | -0.1936 |
| 2026 evaluation, 3 bars | 933 | -0.5215 | 47.70% | -0.8815 |
| 2026 evaluation, 5 bars | 922 | -0.5112 | 49.02% | -0.8712 |

**Interpretation:** 2025 gross averages were not enough to pay even the 0.36 scenario cost. The later 2026 evaluation was negative before transaction costs. Do not tune parameters on either period and then reuse it as independent evidence.

## Triple Barrier / regime diagnostic
Parameters were fixed before the 2025 holdout: 20-bar window, z-threshold 2.0, ATR(14), upper/lower barrier 1 ATR, vertical barrier 10 M15 bars, volatility percentile 0.60, minimum prior history 50.

- 2021–2024: 7,589 barrier-resolved events; direction-aligned first touches 3,768 (49.65%); exact binomial p=0.551; Wilson 95% interval 48.53–50.78%.
- 2025 holdout: 1,830 barrier-resolved events; direction-aligned first touches 947 (51.75%); exact binomial p=0.141; Wilson 95% interval 49.46–54.03%.
- 2025 high-volatility London/NY-filtered subset: 633 resolved events; aligned 327 (51.66%); p=0.427; Wilson 95% interval 47.77–55.53%.
- Across 2021–2025: 9,806 impulses; 219 ambiguous same-candle barrier events. Session labels are provisional because the source timezone/DST convention is not verified.

**Interpretation:** no significant directional edge shown. The binomial tests are naive with overlapping events and serial dependence; their p-values likely overstate precision. No costs are included in the first-touch label test.

## M15 + H1 context, logistic continuation model
Full audit processed the M15 source and aggregated 52,917 complete contiguous H1 bars. H1 context was restricted to bars already closed at the M15 signal time. On the 2025 holdout:

- 3-bar horizon: logistic log-loss 0.69262 vs training-prevalence baseline 0.69171 (worse); Brier 0.24973 vs 0.24928 (worse); holdout n=1,100.
- 5-bar horizon: logistic log-loss 0.69340 vs baseline 0.69273 (worse); Brier 0.25012 vs 0.24979 (worse); holdout n=1,121.
- Expanding-window walk-forward evaluation ran four folds for each horizon. The aggregate report does not establish a repeatable improvement over the simple prevalence baseline. Many subgroup tests were performed; treat individual groups as exploratory even with the built-in BH/FDR adjustment.

**Interpretation:** the model does not demonstrate improved holdout probability quality over a simple baseline. Calibration near 0.5 is not predictive skill.

## Moving-block-bootstrap directional-value tests
The current regime hypothesis diagnostic tested mean signed forward log return over a five-bar horizon. These are diagnostics, not net P&L backtests.

| Dataset | Test observations | Mean signed forward log return | 95% block-bootstrap CI | p-value | Result |
|---|---:|---:|---:|---:|---|
| M1 2021–2025 (latest 50k evaluation window) | 49,978 | -0.00000301 | [-0.00000945, +0.00000452] | 0.428 | Fail to reject zero |
| M1 2020 context (latest 10k window) | 9,998 | -0.00000614 | [-0.00001659, +0.00000770] | 0.322 | Fail to reject zero |
| H1 2021–2025 (latest 10k window) | 9,998 | +0.00003887 | [-0.00005628, +0.00014609] | 0.496 | Fail to reject zero |
| H1 recent 2026 | 568 | -0.00010154 | [-0.00039364, +0.00021003] | 0.486 | Fail to reject zero |
| H4 sample | 895 | +0.00302556 | [+0.00264270, +0.00334821] | 0.002 | Nominally positive, **not edge evidence** |

The H4 result has 877/895 holdout states classified UP and no DOWN states. It is a limited rising-price sample and the test does not compare against an unconditional drift baseline; it cannot demonstrate that the classifier predicted the rise or that a trade could capture it after costs. No multiple-testing correction was applied across timeframes.

## Existing QROS reports checked
- **Phase52 canonical report:** experiment BLOCKED / NOT READY. Reported accuracy was 0.460–0.505 against a 0.690 baseline across feature sets. Its own flags state `data_valid=false`, `out_of_sample=false`, `leakage_check=false`, and `cost_adjusted=false`; therefore it is not valid proof of predictive performance.
- **Phase51 H1 horizon/threshold sweep:** none of the listed 20 combinations passed the Bonferroni significance check; several model accuracies were below the baseline.
- **Legacy walk-forward strategy report:** aggregate total return -77.42, Sharpe -4.77, max drawdown 77.50%, and mean win rate about 19.63% across nine test folds. This is a separate legacy strategy and should not be conflated with the current impulse model, but it is not a successful result.
- **Macro-vs-indicator comparison artifact:** contains unusually strong macro aggregate Sharpe/PF figures but also low average trade counts, infinite reported profit factor, and a macro-factor report with many negative out-of-sample R² folds. These metrics need a fresh audit of units, fold aggregation, and leakage before they can be trusted; they are not accepted as evidence of edge here.
- **FastThreeState daily descriptive check:** 1,466 daily rows; holdout begins 2024-12-23; labels in the tested series were heavily imbalanced (DOWN=3, RANGE=1,257, UP=183). This is insufficient to validate bearish-state behavior and is not a trading P&L test.

## Artifact files written by this audit
- `artifacts/audit_full_m15_triple_barrier_20261017.json`
- `artifacts/candle_velocity_m15_h1_full_audit_20261017.json`
- `artifacts/candle_potential_geometry_full_audit_20261017.json`
- `artifacts/regime_detection_d1_walkforward_20261017.json`
- `artifacts/regime_hypothesis_m1_tail50k_20261017.json`
- `artifacts/regime_hypothesis_m1_2020_context_tail10k_20261017.json`
- `artifacts/regime_hypothesis_h1_2021_2025_tail10k_20261017.json`
- `artifacts/regime_hypothesis_h1_2026_tail10k_20261017.json`
- `artifacts/regime_hypothesis_h4_2023_sample_20261017.json`
- `artifacts/xauusd_horizon_expectancy_2021_2025_cost036_20261017.json`
- `artifacts/xauusd_horizon_expectancy_2026_cost036_20261017.json`

## Decision / next action
1. **Do not optimize this same impulse strategy against the 2025/2026 evaluation windows.**
2. Keep the current signal as a research diagnostic, not a tradable signal.
3. Any new candidate must be tested against a frozen baseline with chronological/purged walk-forward splits, non-overlapping or dependence-aware outcomes, broker-specific historical spread/slippage/commission, and a final untouched holdout.
4. Fix data/metric integrity first where reports are contradictory; especially audit the legacy macro backtest units, low trade counts, and aggregate metrics.
5. Only promote a strategy if net expectancy is positive after realistic costs and uncertainty intervals remain favorable on unseen data. This audit does **not** meet that threshold.
