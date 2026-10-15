# XAUUSD M1 Probability and Trading-Edge Validation

**Scope:** historical research only. No broker execution or live-trading claim.

## Evidence protocol

This protocol separates five claims that must not be conflated:

1. **Pipeline integrity:** data identity, temporal ordering, source/result binding, unique OOS events, reproducible scores.
2. **Probability quality:** Brier score and log loss against a chronological baseline; calibration is assessed on prior realized OOS outcomes only.
3. **Generalization:** walk-forward validation plus a disjoint final holdout; holdout labels cannot fit the estimator or calibration.
4. **Trading economics:** event direction tested after observed spread and explicit slippage stress; compared against always-long and always-short baselines at the same event times.
5. **Deployability:** a portfolio backtest with realistic sizing, order timing, commissions, swaps, market impact, and live fills is a separate requirement.

A pass at one layer is not evidence that later layers pass.

## Reproduction commands

Run from repository root with the configured Python environment:

```powershell
python scripts/audit_xauusd_m1_walkforward.py artifacts/xauusd_m1_walkforward.json
python scripts/run_xauusd_m1_oos_calibration.py artifacts/xauusd_m1_real_events_outcomes.json artifacts/xauusd_m1_walkforward.json --output artifacts/xauusd_m1_oos_calibration_rerun.json
python scripts/audit_xauusd_m1_oos_calibration.py artifacts/xauusd_m1_real_events_outcomes.json artifacts/xauusd_m1_walkforward.json artifacts/xauusd_m1_oos_calibration_rerun.json --output artifacts/xauusd_m1_oos_calibration_audit_rerun.json
python scripts/audit_xauusd_m1_edge_costs.py --output artifacts/xauusd_m1_edge_cost_audit.json
python -m pytest tests/test_audit_xauusd_m1_edge_costs.py -q
```

The data file is local research input and must not be committed. The cost audit verifies the raw CSV SHA-256 against the source artifact before calculating results.

## Required interpretation

- A walk-forward audit passing proves structural and arithmetic invariants for the artifact, not a market edge.
- Brier/log-loss improvement over the chronological baseline is evidence about probability quality, not trade profitability.
- If calibration worsens proper scoring rules, the calibrated probability must not replace the raw probability in downstream decisions.
- Cost results include the observed MT5 spread field (in points) at entry/exit and stress slippage of 0, 1, 2, 5, and 10 points per side. Slippage values are assumptions, not measured historical fills.
- Entry is the next available M1 bar open after the signal; exit is the source-defined realized 1-day endpoint close. Entries with a gap greater than five minutes are excluded.
- Event-level observations may overlap. They are diagnostics, not a deployable equity curve. The non-overlapping diagnostic only accepts the next event after the previous event's realized endpoint; it is still an idealized fixed-horizon event study.
- Commissions, swaps/financing, market impact, and execution latency beyond next-bar entry are not included. Their absence prevents a complete net-profit claim.
- The final holdout must remain untouched while selecting features, thresholds, calibration methods, and cost assumptions. Any post-holdout tuning requires a new future holdout.

## Acceptance gate

Do not label the system as having a proven trading edge unless all of the following hold on a pre-registered, untouched holdout:

- probability scores beat the chronological baseline and uncertainty is quantified;
- calibration does not worsen proper scoring rules and reliability is reported by bin with sample counts;
- the direction strategy beats both simple directional baselines after conservative costs;
- performance survives a documented slippage/commission stress range;
- the strategy is evaluated with non-overlapping portfolio accounting, drawdown, turnover, and risk constraints;
- results reproduce from exact source-data and code hashes;
- negative controls and leakage tests pass.

Otherwise report **EDGE NOT PROVEN**. A failed economic test is a valid result and must not be repaired by retuning on the same holdout.

## Observed local evidence run — 2026-10-15

The following results were computed from the local artifacts bound to these identities:

- Dataset SHA-256: `632950ee767eb8968a00331e6f8da35d3bc73e937bcb3ceb5c1b15f596939da9`
- Source outcome artifact SHA-256: `8a2ba847da994dc0f570b7d63bdae3ff7d976d87260ff0f533a83b26079843e4`
- Walk-forward result SHA-256: `e08786bfe8b944823b1f20087e58112fb8d920f394979ecf5fd79d6cc7a49cc2`
- Cost-audit report SHA-256: `17c5b2ec6a15340cca654be49760331b0efbb6893b539a858838cd46044b220c`
- Calibration artifact SHA-256: `08e88b4abe05dee0e8a8a1123b368e995e8a6a6f167487b222927734b7a041e5`
- Independent calibration-audit report SHA-256: `88d34dd5110babca6997efe26dc8dfdb88f5399834d351adfaf1592d70ba6dd0`
- Cost-audit script SHA-256: `aad98a46590705c65f2f45c69c1d99d93c3d79c622989472801ed45ad778ad85`
- Calibration script SHA-256: `036705a042c523802139eddb3b587b0ff8a076444c43ab22da3e65e30a34c46a`
- Independent calibration-audit script SHA-256: `22f50889e00436e1b8865735c9d893854c4b9d6ef78fe04790453f8c54684aa1`

### Probability

- Independent walk-forward structural audit: **PASS** — 44 folds, 22,000 unique OOS validation events, 500 final-holdout predictions, no audit failures.
- Walk-forward OOS model: Brier **0.2489701**, log loss **0.6910857**.
- Walk-forward chronological baseline: Brier **0.2500046**, log loss **0.6931564**.
- Final holdout (500 events): model Brier **0.2421406**, log loss **0.6774056**; baseline Brier **0.2500087**, log loss **0.6931645**.
- Causal isotonic calibration was independently audited against the current result SHA. It **degraded** the proper scores: raw Brier **0.2489784** → calibrated **0.2523406**; raw log loss **0.6911023** → calibrated **0.7020845**. The calibration artifact now explicitly reports `DEGRADED` and `BLOCK_CALIBRATED_PROBABILITIES`. Do not consume those calibrated probabilities downstream.

### Spread/slippage diagnostic

The new cost audit verifies the dataset SHA before calculation, uses observed entry/exit spread points, enters at the next M1 bar open, and exits at the source-defined realized endpoint. Slippage is stressed at 0/1/2/5/10 points per side.

- 24,850 source events; 24,826 had usable entry/exit bars; 24 skipped because next-bar entry was more than five minutes after the signal. The full-history event set yields 1,289 non-overlapping fixed-horizon events.
- Final holdout: 500 predictions; 498 had cost inputs; 2 were explicitly excluded and listed in the output. The non-overlapping final-holdout diagnostic contains **26 trades**.
- Compounded returns are deliberately omitted from overlapping-event diagnostics; overlapping event returns are not a valid portfolio equity curve.
- At 0 slippage points per side, signal mean return was **0.5691%** per event versus **0.1871%** for always-long on the same timestamps. Paired mean difference: **+38.19 bps**, bootstrap 95% interval **−6.13 to +107.69 bps**.
- At 10 slippage points per side, signal mean return was **0.5644%** versus **0.1824%** always-long; the paired interval still includes zero.
- The interval is a deterministic IID bootstrap and is **not adjusted for serial dependence**. Only 26 non-overlapping holdout trades are available. Broker commission, swap/financing, market impact, and measured live slippage are not included.

### Decision

**Trading edge: NOT PROVEN.** The point estimate is positive against the always-long benchmark in this small retrospective holdout diagnostic, but its uncertainty interval includes zero, two of 500 holdout events lack cost inputs, and full net execution costs are incomplete. The observed probability calibration is explicitly rejected for downstream use. This result is a reason to collect a new untouched holdout and complete a commission-inclusive portfolio simulation—not a reason to tune the current holdout.

### Local implementation verification

- C++ engine full build: `cmake --build .qros-build-native --config Release --target ALL_BUILD` — exit code 0.
- Constraint-first C++ binding rebuild after fail-closed exception fix — exit code 0; constraint-first tests **12 passed**.
- Native quant integration/regression suite: **142 passed, 2 skipped**.
- Probability calibration, independent audit, walk-forward audit, and cost-audit tests: **20 passed**.
- Full configured local Python suite with the native backend import path set: **4,398 passed, 19 skipped**.
- Targeted Ruff check and format check passed; targeted mypy returned `Success: no issues found in 3 source files`.

These are local Windows/Python 3.12 results. GitHub CI for the new commit must still pass before the change is considered merged or release-ready.
