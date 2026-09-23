# Phase 5.2 rebuild

The previous Phase 5.2 evidence runner is retired as a scientific execution path.

Reason: the prior implementation mixed calendar alignment, feature warm-up/label eligibility, and experiment gating, producing a 1246 common sample while the canonical four-way calendar audit was 1289, without a sufficiently explicit accounting boundary.

## Rebuild contract

1. Preserve raw source files unchanged.
2. Independently audit each source before alignment.
3. Build and audit the exact four-way timestamp intersection separately.
4. Report every row-loss stage explicitly: calendar intersection, feature warm-up, label horizon, and final usable sample.
5. Never fabricate OHLC from scalar macro observations.
6. Never reduce training requirements merely to bypass an insufficient-sample block.
7. Only after the data ledger is internally consistent may walk-forward OOS, costs, calibration, significance, and final evidence be executed.

This is a rebuild boundary, not a scientific result.
