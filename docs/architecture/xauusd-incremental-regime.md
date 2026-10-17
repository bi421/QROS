# XAUUSD incremental market-regime engine

## Purpose

This is a research-only detector for UP, DOWN, and RANGE states. It does not submit or execute orders. Its state probabilities are smoothed empirical state-transition frequencies, not calibrated probabilities of a profitable trade.

## Large historical files

Run a local OHLC CSV with bounded-memory chunks and pandas memory-map reader:

    Set-Location "C:\Users\User\Desktop\QROS"
    .\.venv\Scripts\python.exe scripts\run_xauusd_regime_stream.py "data\curated\xauusd\xauusd_h1_2026_recent_real.csv" --chunksize 100000 --output "$env:TEMP\qros-regime-stream.json"

The reader validates chronological, unique timestamps and hashes the exact source file. It processes one chunk at a time and feeds candles into a bounded-state engine. This avoids retaining the full historical dataset in RAM. SHA-256 currently requires a separate full-file read for provenance.

## Incremental update path

IncrementalRegimeEngine.update(high, low, close) consumes one completed candle. Rolling price regression statistics, return variance, directional movement, true range, ADX windows, and transition counts are maintained between calls. Hurst is a diagnostic refreshed every N bars; it does not decide the regime.

The update cost is bounded by configured lookback/indicator windows and does not grow with the total historical row count. The Python implementation is a reference implementation. For a 1-billion-row backfill, expect a long batch job, not milliseconds; the local synthetic benchmark must not be extrapolated to a different disk, CPU, CSV width, or validation workload. A newly received candle can be processed much faster than rescanning history, but latency guarantees require repeated benchmarks on the target machine and real feed.

## Validation boundary

- Unit tests validate state contracts, bounded rolling buffers, chunk parsing, and timestamp rejection.
- Reported rows_per_second is measured for the streaming parse/feature path and excludes the separately timed SHA-256 pass.
- Current state is a heuristic label; transition probabilities are not calibrated forecasts.
- Forward-return summaries do not include spread, commission, slippage, funding, or confidence intervals.
- No trading edge is claimed. A proper walk-forward evaluation needs leakage controls, uncertainty intervals, and a broker-specific net-cost model.
- The repository currently has no live market-data feed connected to this CLI. The input file's last timestamp must be checked before calling any result current.
