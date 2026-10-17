# QROS Research Controls V2

Research-only validation layer. No function authorizes broker execution.

## Gate contract

`unified_research_gate` no longer accepts caller-supplied booleans or a caller-supplied robustness score. It requires ordered trade-level net returns, a declared number of tested trials, cost provenance metadata, and chronological fold return series. Missing inputs return a fail-closed status; the removed boolean interface raises `TypeError`.

The gate computes:

- Moving-block bootstrap percentile 95% confidence interval for the mean net return.
- A one-sided centered-null block-bootstrap p-value.
- A conservative trial-count bound `min(1, p * tested_trial_count)`.
- Minimum sample-size check.
- Walk-forward fold stability from the fraction of folds with positive mean returns.
- Structural cost provenance checks for source, units, spread-log SHA-256, coverage count, commission/slippage models, and the declared net-of-cost return basis.

**Multiple-testing limitation:** The API currently receives one candidate return series plus the total trial count, not every trial's p-value. Therefore `min(1, p * m)` is a conservative sufficient bound for a Benjamini-Hochberg pass, not the exact family-wide BH-adjusted p-value. A non-passing bound means the candidate does not pass this gate; exact BH reporting requires preserving and passing p-values for all trials. Cost metadata structure also cannot independently prove that a source or vendor log is truthful.

## Fail-closed production pipeline behavior

The existing frozen XAUUSD M1 worker path now writes `research_gate` and `research_audit` into the meta-evaluation artifact. The current frozen workflow does not supply verified all-in spread/commission/slippage evidence or trade-level net returns. Therefore it deliberately returns `NO_TRADE_COST_PROVENANCE_INVALID`; gross forward outcomes are not relabelled as net returns. The audit records dataset SHA, upstream artifact hashes, decision hash, config version, and the runtime source-commit declaration. Set `QROS_SOURCE_COMMIT` in the runtime environment to provide the actual source SHA; otherwise the audit explicitly records `UNDECLARED_RUNTIME_SOURCE_COMMIT`.

## XAUUSD BNF-style diagnostic

`apply_bnf_mean_reversion` uses a rolling price-deviation z-score and lower 1% / 5% quantiles calculated only from prior observations (`shift(1)`). It does not use fixed -35% / -20% price-deviation thresholds. The turnover filter is disabled by default because `close * tick_volume` is not a reliable economic notional for CFD data; callers may enable a capacity cap only when the volume field has valid economic units.

Run the timeframe diagnostic:

```powershell
python scripts\audit_qros_bnf_timeframes.py
```

The report covers M15/H1/H4/D1 signal counts, NO_TRADE fractions, and gross 1/3/5-bar forward-return distributions. These are descriptive diagnostics only: they do not include costs, do not establish an edge, and are not used as proof for the frozen M1 gate.

Audit the historical MT5 spread field:

```powershell
python scripts\audit_xauusd_spread_log.py
```

The retained M1 source contains 1,764,176 spread observations (median 9, p90 19, p95 32, p99 35, maximum 1,017 in MT5-native spread points). The point-to-price conversion is not verified, and commission/slippage models are absent, so this is **spread data present, all-in cost evidence still incomplete**.

## Frozen FOLLOW evidence

The historical vectorized-backtest document reports 19 of 324 gross paired FOLLOW-minus-REVERSE intervals wholly above zero. The checked-in full-grid benchmark artifact contains candidate-level aggregate summaries, not the 19 paired per-trade net-return series or verified broker-cost logs. These 19 cannot honestly be rerun through a net-return gate until those paired returns and cost evidence are preserved. They must be classified as **not re-evaluable / evidence missing**, not as 19 confirmed edges or 19 statistically rejected edges.

## Kelly and C++ boundary

The earlier Kelly sizing helper and native C++ prototype are retained but frozen. A point-estimate Kelly result is not an edge-validation result; it remains research-only and does not authorize execution. The C++ BNF prototype retains the previous fixed thresholds and is not used by the new Python z-score diagnostics. Its parity test has been removed because the methods no longer implement the same specification.
