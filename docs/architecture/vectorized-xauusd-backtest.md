# Vectorized XAUUSD Backtest v1

## Purpose and safety

Research-only; never places orders. The engine evaluates a bounded parameter grid on OHLCV, enters at the next bar open after a completed-bar signal, applies ATR-scaled asymmetric TP/SL barriers, uses stop-first resolution when both barriers are touched in the same candle, rejects signals crossing timestamp gaps, and writes a JSON audit report. Missing or unverified all-in costs fail closed. A passing candidate is not a certified production edge; it requires an independent untouched final holdout.

## Inputs

- Headerless MetaTrader CSV: `timestamp,open,high,low,close,tick_volume,real_volume`; UTF-16 LE and UTF-8 supported through a cached UTF-8 conversion for UTF-16 source files.
- Optional news CSV with `timestamp`, `time`, `datetime`, or `date` column. The news timestamps must be timezone-aligned to the broker candle timestamps by the data owner. No news data is inferred if the file is absent.
- The current XAUUSD M15 CSV has no spread column; costs cannot be inferred from OHLCV alone.

## Evaluation contract

- Causal signal: close-to-close move normalized by historical ATR scale; signal is known at close `i`.
- Entry: open of bar `i+1`.
- Triple barrier: TP/SL distances are ATR multiples from entry; scan future OHLC bars, stop-loss takes precedence if both hit in the same candle; otherwise time exit at close of the configured horizon.
- Session gaps: candidates are excluded when their feature lookback or forward barrier horizon crosses a non-15-minute timestamp gap.
- Cost: `base_spread_price + alpha_cost_price * (ATR / trailing_mean_ATR) + commission_roundtrip_price`. All inputs are round-trip XAUUSD price units per ounce and require conversion against broker contract/commission specifications. The `--cost-model-verified` flag is an operator attestation, not automatic broker verification.
- Statistics: chronological final 20% holdout, 20-observed-trading-day circular block bootstrap, one-sided bootstrap p-values and Benjamini-Hochberg FDR correction. This v1 is an event-study screening tool: candidate events can overlap, so results are not a single-position account-equity simulation. Candidate selection and holdout reuse still require an independently untouched confirmation dataset.

## Run

```powershell
$env:PYTHONPATH='.'
python scripts\run_vectorized_xauusd_backtest.py --quick --bootstrap-replicates 100 --output artifacts\vectorized_xauusd_backtest_smoke_20261017.json
```

The full default grid is 972 candidates and is intentionally not run in the smoke test. A quick run checks two parameter combinations. Do not extrapolate smoke-test runtime to a 972-candidate or million/billion-combination sweep. Billion-scale search in under 100 ms is not a defensible expectation for path-dependent OHLC triple barriers plus statistical correction; use staged screening, compiled kernels, and independent validation.

## Current evidence and limitations

- Local smoke input: 211,868 M15 rows, 2017-10-10 01:00 through 2026-10-14 06:15.
- Latest quick run: two candidates, 100 bootstrap replicates; data load 0.035 s, evaluation 0.106 s, total 0.142 s on the current Windows host. These are one-run local timings, not a stable benchmark.
- Status: `NO_TRADE_COST_AUDIT_UNVERIFIED`; no spread/commission evidence was supplied, so net expectancy and edge certification are withheld.
- No news CSV or live-candle feed was located in the inspected Documents data listing; news filter reports `NOT_CONFIGURED`. Live ingestion is not part of this offline CSV runner.
- SIMD/AVX-512 and C++ acceleration are not claimed by this NumPy/Polars v1. The existing C++ backtest is separate and has not been replaced.
