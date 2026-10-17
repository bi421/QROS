# QROS vs VectorBT — signal-stage microbenchmark

Date: 2026-10-17

## Result

This is a **signal-generation microbenchmark only**, not a full backtest-engine ranking. QROS's NumPy implementation and a VectorBT 1.1.2 custom Numba indicator computed the same XAUUSD M15 score on the same dataset. Outputs matched with `rtol=1e-12`, `atol=1e-12`, and equal NaNs.

| Measurement | QROS NumPy | VectorBT 1.1.2 custom Numba indicator |
|---|---:|---:|
| Dataset rows | 211,868 | 211,868 |
| Median steady-state score time (5 runs) | 0.012658 s | 0.019102 s |
| Throughput | 16.74 million rows/s | 11.09 million rows/s |
| First call / JIT compile | No JIT compile | 1.442 s including first-run compilation |
| Score parity | Reference | Exact within declared floating-point tolerance |

QROS was approximately 1.51× faster for this single signal calculation on this machine. This result does not establish that QROS's full backtest engine is faster than VectorBT.

## Locked input and rule

- File: local `XAUUSDM15.csv` used by the Windows research environment.
- SHA-256: `bc574cba7eedca456333ee736adf81639f379ed58213e18e076b9b7003783e0b`.
- Observed timestamp range: `2017-10-10 01:00` through `2026-10-14 06:15`.
- Rule: `(close[t] - close[t-lookback]) / mean(ATR[t-lookback:t])`, with `lookback=8`; invalidate the score when a 15-minute data gap crosses the lookback window.
- Signal threshold used for the separate QROS single-candidate run: `abs(score) >= 1.0`; TP=1 ATR, SL=1 ATR, horizon=8 bars, no news filter.
- QROS single-candidate full event simulation took 0.100932 s and emitted 96,962 candidate trade events. The candidate status was `NO_TRADE_COST_AUDIT_UNVERIFIED` because broker cost evidence was not supplied.
- Environment: Windows; Python 3.12.10; QROS NumPy 2.5.2 / Polars 1.44.1; isolated VectorBT environment with VectorBT 1.1.2 / NumPy 2.5.4.

## What this does not prove

- The VectorBT side used a custom Numba indicator for the score formula. It did **not** run VectorBT portfolio accounting or match QROS's TP/SL stop-first, gap-fill, time-out, overlapping event, commission, spread or slippage semantics.
- RSS was observed in the VectorBT process, but peak-memory measurement and a like-for-like QROS memory measurement were not collected.
- No edge is established. Costs are unverified and the QROS run intentionally fails closed.

## LEAN status

LEAN was not benchmarked: the environment had no `lean` CLI, no .NET SDK, and no preloaded QuantConnect LEAN Docker image. Docker Engine itself was available. A valid LEAN comparison still needs a reproducible algorithm adapter implementing the same event timing, barrier ordering, gap fills, cost model, and event/position accounting. Do not compare its results until that parity is tested.

## Next benchmark gate

1. Implement one shared locked trade ledger / fill specification.
2. Add VectorBT and LEAN adapters that match entry-at-next-open, intrabar stop-first barriers, gap-stop fills, timeout close, overlapping-signal semantics, and cost units.
3. Verify trade-by-trade exits and PnL against a small hand-calculated fixture before measuring runtime or RAM.
4. Run the same frozen dataset/config repeatedly and report result hashes, wall time, peak RSS and rows/trades per second.
