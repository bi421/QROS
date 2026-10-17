# Vectorized XAUUSD Backtest v2

## Purpose and safety

Research-only; never places orders. The engine evaluates a bounded parameter grid on OHLCV, enters at the next bar open after a completed-bar signal, applies ATR-scaled asymmetric TP/SL barriers, uses stop-first resolution when both barriers are touched in the same candle, rejects signals crossing timestamp gaps, and writes a JSON audit report. Missing or unverified all-in costs fail closed. A passing candidate is not a certified production edge; it requires an independent untouched final holdout.

## Inputs

- Headerless MetaTrader CSV: `timestamp,open,high,low,close,tick_volume,real_volume`; UTF-16 LE and UTF-8 supported through a cached UTF-8 conversion for UTF-16 source files.
- Optional news CSV with `timestamp`, `time`, `datetime`, or `date` column. The news timestamps must be timezone-aligned to the broker candle timestamps by the data owner. No news data is inferred if the file is absent.
- The current XAUUSD M15 CSV has no spread column; costs cannot be inferred from OHLCV alone.

## Evaluation contract

- Causal signal: close-to-close move normalized by historical ATR scale; signal is known at close `i`.
- Entry: open of bar `i+1`.
- Triple barrier: TP/SL distances are ATR multiples from entry; scan future OHLC bars, stop-loss takes precedence if both hit in the same candle; a stop crossed by an opening gap fills at the worse bar-open price, otherwise at the stop level; time exit is at close of the configured horizon. Take-profit fills at its limit level for conservative, reproducible OHLC handling.
- Session gaps: candidates are excluded when their feature lookback or forward barrier horizon crosses a non-15-minute timestamp gap.
- Cost: `base_spread_price + alpha_cost_price * (ATR / trailing_mean_ATR) + commission_roundtrip_price`. All inputs are round-trip XAUUSD price units per ounce and require conversion against broker contract/commission specifications. The `--cost-model-verified` flag requires `--cost-evidence-file`; its SHA-256 is recorded for traceability, not as independent proof that the broker cost evidence is correct. Source rows must already be strictly chronological and unique; the loader rejects rather than silently sorts them.
- Statistics: chronological final 20% holdout, 20-observed-trading-day circular block bootstrap, two-sided 95% percentile interval, separate one-sided positive/negative bootstrap p-values, and separate Benjamini-Hochberg FDR correction for each direction of claim.
- Directional mirror study: every parameter candidate is evaluated as FOLLOW_SIGNAL and REVERSE_SIGNAL on identical signal timestamps, entry bars, and parameter settings. A paired holdout difference (FOLLOW_SIGNAL minus REVERSE_SIGNAL) is bootstrapped over the same event indices. Positive difference means following the signal did better; negative means reversing did better. Directional comparison is classified as UNVERIFIED_COSTS, INCONCLUSIVE, FOLLOW_SIGNAL_BETTER_REQUIRES_INDEPENDENT_CONFIRMATION, or REVERSE_SIGNAL_BETTER_REQUIRES_INDEPENDENT_CONFIRMATION. The last two labels are screening outcomes, not certified trading edges.
- A strategy is REJECTED_NEGATIVE_EDGE only when the upper 95% interval is below zero and its negative-edge p-values pass FDR. An interval spanning zero is INCONCLUSIVE, not proof of profitability or unprofitability. Missing/unverified broker costs continue to fail closed.
- Bootstrap block totals use prefix sums to avoid materializing a full replicate-by-day index tensor. The final reduction uses ndarray.sum: this is a small reduction, not dense matrix multiplication, so einsum(optimize=True) or BLAS GEMM is not assumed to be faster. This remains an event-study screening tool: candidate events can overlap, so results are not a single-position account-equity simulation. Candidate selection and holdout reuse still require an independently untouched confirmation dataset.

## Run

```powershell
$env:PYTHONPATH='.'
python scripts\run_vectorized_xauusd_backtest.py --quick --bootstrap-replicates 100 --output artifacts\vectorized_xauusd_mirror_smoke_20261017.json
```

With a news CSV configured, the full default grid has 972 parameter combinations evaluated in both directions (1,944 directional candidates). Without a news CSV, ineffective news-buffer variants are collapsed, leaving 324 parameter combinations and 648 directional candidates. A quick run checks two parameter combinations in both directions (four directional candidates). Do not extrapolate smoke-test runtime to the full grid or a million/billion-combination sweep. Billion-scale search in under 100 ms is not a defensible expectation for path-dependent OHLC triple barriers plus statistical correction; use staged screening, compiled kernels, and independent validation.

## Current evidence and limitations

- Current real-data smoke input: 211,868 M15 rows, 2017-10-10 01:00 through 2026-10-14 06:15.
- Directional mirror smoke: four directional candidates (two parameter combinations × two directions), 100 bootstrap replicates; final rerun data load 0.035 s, evaluation 0.207 s, total 0.242 s on the current Windows host.
- Full mirror grid without a news CSV: 648 directional candidates across 324 parameter combinations and 324 paired comparisons; 100 bootstrap replicates; data load 0.315 s, evaluation 56.605 s, total 56.920 s on the current Windows host.
- Across the full grid, 209 paired gross expectancy differences favored FOLLOW_SIGNAL and 115 favored REVERSE_SIGNAL. Of 324 gross-difference diagnostic intervals, 19 were wholly above zero, none were wholly below zero, and 305 spanned zero. These are gross-only diagnostics; because broker costs are unverified, the pipeline intentionally withheld p-value/FDR claims and all net expectancy values.
- Status: NO_TRADE_COST_AUDIT_UNVERIFIED; no independently verified spread/commission/slippage model was supplied, so net expectancy and directional edge claims are withheld.
- Historical pre-mirror benchmark: the previous implementation took 80.144 s for 972 candidates with 100 bootstrap replicates. The current no-news grid is smaller because redundant news-buffer variants are collapsed; timings are single-run measurements, not benchmark distributions.
- No news CSV or live-candle feed was located in the inspected Documents data listing; news filter reports NOT_CONFIGURED. Live ingestion is not part of this offline CSV runner.
- SIMD/AVX-512 and C++ acceleration are not claimed by this NumPy/Polars implementation. The existing C++ backtest is separate and has not been replaced.
