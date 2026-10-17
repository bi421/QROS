# QROS XAUUSD regime hypothesis testing

## Goal and null hypothesis

The optional offline diagnostic tests:

- H0: mean signed forward log return is zero.
- H1: mean signed forward log return differs from zero.

For each completed candle t, the state at t maps to a position sign (UP=+1, DOWN=-1, RANGE=0). Outcome is log(close[t+h]/close[t]). The test uses only a chronological tail holdout; it does not shuffle time. A moving-block bootstrap estimates a two-sided p-value and a 95% interval while partially allowing serial dependence.

## Run explicitly; never part of the live update path

    Set-Location "C:\Users\User\Desktop\QROS"
    .\.venv\Scripts\python.exe scripts\run_xauusd_regime_hypothesis.py "data\curated\xauusd\xauusd_h1_2026_recent_real.csv" --chunksize 256 --horizon 5 --max-observations 500 --bootstrap-replicates 199 --output "$env:TEMP\qros-regime-hypothesis.json"

The command has no network, database, or order-execution path. It processes CSV chunks and stores only a bounded tail buffer of at most 2 * max_observations + horizon + 1 bars. It is an explicit offline job, not a background service, and is never called by IncrementalRegimeEngine.update. On Windows it requests below-normal process priority on a best-effort basis. Keep the observation cap and bootstrap count low for a light diagnostic; increase only in a separate research run when resources allow.

## Interpretation

- p >= 0.05: fail to reject H0. This does NOT prove the regime has no predictive value.
- p < 0.05: reject H0 for the specified holdout/horizon/test only. This does NOT prove causal predictability or net trading profitability.
- The current state labels are heuristic and must be frozen before a final holdout is examined.
- Overlapping forward returns, repeated horizons/parameter trials, small state counts, and non-stationarity can invalidate naive conclusions. Pre-register one horizon; use multiplicity correction if testing many horizons.
- Costs (spread, commission, slippage, latency), calibration, confidence intervals for subgroup states, and broker-specific fills are not included.
- No automatic strategy activation or order execution follows from the result.
