# QROS Unified Edge Validation Suite

Version: `EDGE_VALIDATION_SUITE_V1`

## Purpose and safety boundary

This module connects statistical diagnostics into a reproducible research audit. It is not an order router and does not execute trades. The decision gate can only produce `CANDIDATE_FOR_FURTHER_REVIEW` or `NO_TRADE`; it always returns `execution_authorized: false`.

A passed software test proves the implementation behaves as tested. It does not prove profitability. A robustness score of 0.90 is the fraction of applicable predeclared attacks passed, not a 90% probability that an edge is real.

## Implemented primitives

- `quarter_kelly`: estimates win probability and mean win/loss payout ratio from trade outcomes normalized to the capital at risk (for example, R-multiples); applies a fractional Kelly multiplier and a hard maximum fraction. Raw dollar PnL alone is not a defensible sizing input. It returns zero for non-positive expectancy, insufficient trade count, or missing win/loss diversity. The output is diagnostic only.
- `outcome_dependence`: reports autocorrelation of signed outcomes and conditional win rates after runs. It does not assume that a losing streak is due to reverse and does not automatically change position size.
- `moving_block_bootstrap_ci`: reproducible moving-block percentile interval for mean net outcome. `block_length` is measured in input rows. Twenty means twenty trades if the ledger contains trades; it does not automatically mean 20 calendar days. Choose the block length from the data frequency and dependence horizon before evaluating holdout data.
- `five_attack_overfitting_suite`: chronological chunk stability, best-regime removal, top-five contributor removal, random trade omission, and best-asset removal. Best-asset removal is not applicable to a single-asset XAUUSD-only experiment. Regimes must be specified ex ante. The random omission test is not a model of clustered slippage or missed fills.
- `incremental_log_likelihood_test`: compares baseline and augmented probabilistic forecasts on the same binary outcomes. The naive likelihood-ratio p-value is meaningful only for genuinely nested models with the required regularity conditions; for separately trained models, use a preregistered paired out-of-sample test. Apply FDR across the full hypothesis family.
- `cusum_change_points`: two-sided CUSUM anomaly flags with reference parameters that must be frozen from training data. It reports structural change diagnostics, not trade signals.
- `research_decision_gate`: requires positive net expectancy, positive lower bootstrap CI, robustness score at least 0.90, FDR pass, verified costs, sufficient sample and point-in-time-valid data. Any missing/failed item yields `NO_TRADE`.

## Formula notes

For binary win/loss outcomes with win probability (p) and payoff ratio (b = \bar{W}/|\bar{L}|):

`f_full = p - (1-p)/b`

`f_fractional = gamma * f_full`, with `gamma = 0.25` for quarter-Kelly.

The code's cap is a maximum account fraction, not a promise that the trade risks that exact fraction. Estimation error, tails, leverage, gaps, dependence, and changing regimes can make Kelly sizing unsafe. Do not use Kelly on gross or in-sample PnL.

For a block bootstrap of mean net expectancy, the acceptance check is `CI_lower > 0`, but only after point-in-time, cost, sample-size and multiple-testing checks. This alone does not establish future edge.

## CLI

Input CSV must be a frozen trade ledger with a `net_pnl` column. Optional `r_multiple` contains each trade's net outcome in units of capital at risk; without it, the CLI refuses to calculate Kelly sizing. Optional `asset` and `regime` columns enable the corresponding removal attacks. Optional `outcome_binary`, `baseline_probability`, and `augmented_probability` columns must be supplied together to run the information-gain diagnostic.

```powershell
python scripts\audit_edge_validation_suite.py `
  --input .\artifacts\frozen_trade_ledger.csv `
  --output .\artifacts\edge_validation_audit.json `
  --block-length 20 `
  --bootstrap-repetitions 2000 `
  --omission-repetitions 1000 `
  --seed 421
```

No production ledger or live Quiver fetch is performed by this CLI unless explicitly supplied. The output is a research artifact, not an execution instruction.

## Still external / not proven

- Broker/account cost evidence and realistic fill/slippage model.
- Quiver credential, entitlement, live authenticated request, pagination and historical completeness.
- Verified open-market classification and stable insider identity mapping.
- Preregistered family of all tried hypotheses and valid FDR/DSR/SPA procedure for the actual experiment.
- XAUUSD holdout edge and the incremental predictive value of alternative data.
- Production integration, UI/API exposure, and live execution (intentionally out of scope).

## Test scope

The module has deterministic unit tests for Kelly, streak/autocorrelation diagnostics, block-bootstrap reproducibility, five attacks, log-likelihood comparison, CUSUM and fail-closed decision logic. These tests do not validate the scientific hypothesis or vendor data.
