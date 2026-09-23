# Phase 5.2 Context Sensitivity Interpretation

## Verified local execution

The user executed `run_phase52_rebuild_context_boundary_sensitivity.py` on the real local dataset.

- Research rows: 1246
- Pre-research context state rows: 83
- Comparison rows: 1181
- Labels remained identical across context-seeded and cold-start datasets.
- Source equivalence remains unproven.

## Observed sensitivity

| Feature set | Max absolute difference | Mean absolute difference | Different values |
|---|---:|---:|---:|
| PRICE_ONLY | 0.317591981204 | 0.00019310322291 | 346 / 22439 |
| PRICE_DXY | 0.317591981204 | 0.000166770965241 | 346 / 25982 |
| PRICE_US10Y | 0.317591981204 | 0.000166770965241 | 346 / 25982 |
| PRICE_VIX | 0.317591981204 | 0.000166770965241 | 346 / 25982 |
| PRICE_ALL | 0.317591981204 | 0.000131034329832 | 346 / 33068 |

## Scientific interpretation

This is a structural sensitivity PASS, not evidence that context effects are negligible. The mean differences are small, but the maximum difference of approximately 0.318 requires investigation of which feature and research day produced it. The audit must therefore remain descriptive until the difference distribution and affected-feature identity are inspected.

The context source is permitted only as pre-research rolling state under the explicit context-use contract; it is not treated as equivalent to the canonical MT5 XAUUSD source.

## Next gate

Before estimator/backtest execution, identify the affected feature/day distribution and verify that labels, source-day identity, feature names, and chronological boundaries remain invariant.
