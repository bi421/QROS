# Quant Math Audit Integration v1

## Runtime contract

```python
from researchos.quant_math.engine import QuantMathEngine

report = QuantMathEngine().evaluate_with_audit(
    prices=prices,
    successes=successes,
    failures=failures,
    monte_carlo_simulations=10_000,
    seed=42,
)
```

The existing `evaluate()` contract is unchanged. `evaluate_with_audit()` returns the original result and its hash plus an audit evidence list and aggregate audit status.

## Status semantics

- `VERIFIED`: every currently attached audit reproduced its specified arithmetic/replay contract within tolerance.
- `FALSIFIED`: at least one reported checked claim contradicts an independent calculation.
- `INVALID_INPUT`: at least one audit contract cannot be evaluated due to invalid evidence, unless another checked claim was already falsified.
- `INCONCLUSIVE`: no supported audit was run, or at least one attached check cannot establish the claim.

The `profitability_verdict` is deliberately `NOT_ASSESSED_BY_MATHEMATICAL_AUDIT`. Mathematical replay is not a profitability test.

## Current coverage

- Descriptive statistics (mean, population variance/standard deviation, range, last-observation z-score, correlation, and linear regression): independently recomputed from the ordered raw prices.
- Monte Carlo terminal summary: replayed independently from the input prices, simulation count, and seed.
- Existing engine API: preserved, with an opt-in audited method.
- Bayesian posterior and Monte Carlo replay audits run only when those optional outputs are requested.

## Explicitly not established

This integration does not yet independently test GBM assumptions, calibration, time dependence, leakage, multiple testing, execution costs, or out-of-sample strategy edge. A verified replay does not establish that the return-resampling assumption describes future markets. Missing positive evidence is not automatically evidence of negative profitability.

## Release requirements

Before calling this production-ready, run the repository's supported CI on the exact merge SHA, add independent diagnostics for the remaining models, connect immutable input/code provenance to persisted research-run evidence, and verify tenant/auth/workspace isolation and operational recovery. No production database is modified by this change.
