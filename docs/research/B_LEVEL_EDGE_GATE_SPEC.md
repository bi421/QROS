# B-Level XAUUSD M1 Edge Validation Gate

## Purpose

Define the statistical gate used to decide whether the frozen XAUUSD M1 walk-forward probability study contains reproducible predictive information. This document does not define a trading strategy or profitability claim.

## Frozen hypothesis

**H0:** the frozen direction-conditional OOS probability model does not improve probabilistic forecast quality over the frozen per-fold historical-rate baseline.

**H1:** the frozen OOS model improves probabilistic forecast quality over that baseline.

Primary metric: Brier improvement = baseline Brier score minus model Brier score. Positive values favor the model.

## Required evidence

1. Use only the already-produced chronological OOS predictions.
2. Do not refit the model during this evaluation.
3. Verify the walk-forward artifact independently before evaluation.
4. Require at least 10,000 unique OOS validation events.
5. Require positive aggregate Brier improvement.
6. Require the 95% confidence interval for fold-level improvement to remain above zero.
7. Require paired permutation significance below 0.01.
8. Require a two-sided sign test below 0.05.
9. Require improvement in at least 70% of OOS folds.

## Interpretation

- **B_LEVEL_PASS:** every gate above passes.
- **NO_EDGE_OR_INCONCLUSIVE:** one or more gates fail.

A B_LEVEL_PASS is evidence of predictive probability improvement only. It is **not** evidence of guaranteed profit, executable trading performance, or live-market performance.

## Negative controls

Any future B-level result must also be checked against label-shuffle and temporal-leakage negative controls. A result that survives only the primary test but fails a negative control is rejected.

## Provenance

The evaluation must record the exact walk-forward artifact SHA-256, contract, OOS sample count, fold count, statistical seed, and all gate outputs.
