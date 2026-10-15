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
python scripts/audit_xauusd_m1_probability_skill.py --output artifacts/xauusd_m1_probability_skill_audit.json
python scripts/audit_xauusd_m1_edge_costs.py --source artifacts/xauusd_m1_real_events_outcomes.json --data data/mt5/xauusd/XAUUSD_M1_2021_2025_MT5.csv --walkforward artifacts/xauusd_m1_walkforward.json --output artifacts/xauusd_m1_edge_cost_audit_commission_rerun.json
python -m pytest tests/test_audit_xauusd_m1_probability_skill.py tests/test_audit_xauusd_m1_edge_costs.py researchos/tests/test_xauusd_m1_oos_calibration.py researchos/tests/test_xauusd_m1_oos_calibration_audit.py tests/test_audit_xauusd_m1_walkforward.py -q
```

The data file is local research input and must not be committed. The cost audit verifies the raw CSV SHA-256 against the source artifact before calculating results.

## Required interpretation

- A walk-forward audit passing proves structural and arithmetic invariants for the artifact, not a market edge.
- Brier/log-loss improvement over the chronological baseline is evidence about probability quality, not trade profitability.
- If calibration worsens proper scoring rules, the calibrated probability must not replace the raw probability in downstream decisions.
- Cost results include the observed MT5 spread field (in points) at entry/exit and stress slippage of 0, 1, 2, 5, and 10 points per side. Generic round-trip commission assumptions of 0, 1, 2, 5, and 10 basis points of notional are also reported separately. Neither stress grid is a broker quote or measured fill cost.
- Entry is the next available M1 bar open after the signal; exit is the source-defined realized 1-day endpoint close. Entries with a gap greater than five minutes are excluded.
- Event-level observations may overlap. They are diagnostics, not a deployable equity curve. The non-overlapping diagnostic only accepts the next event after the previous event's realized endpoint; it is still an idealized fixed-horizon event study.
- The cost audit now subtracts a generic commission-bps stress from each completed trade and reports maximum drawdown for the idealized non-overlapping compounded sequence. These bps are not mapped to a broker's per-lot schedule; swaps/financing, market impact, and execution latency beyond next-bar entry remain excluded. The drawdown is a diagnostic at implicit 100% equity allocation per trade, not a recommended sizing rule or broker-executable portfolio simulation.
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

**Reproduction note:** the commission sensitivity grid was recomputed on 2026-10-15 against the exact local CSV, source outcome artifact, and walk-forward artifact. The complete JSON result is recorded at artifacts/xauusd_m1_edge_cost_audit_commission_rerun.json (SHA-256 below). CI tests use synthetic fixtures and do not recreate the full local-market-data audit.

The following results were computed from the local artifacts bound to these identities:

- Dataset SHA-256: `632950ee767eb8968a00331e6f8da35d3bc73e937bcb3ceb5c1b15f596939da9`
- Source outcome artifact SHA-256: `8a2ba847da994dc0f570b7d63bdae3ff7d976d87260ff0f533a83b26079843e4`
- Walk-forward result SHA-256: `e08786bfe8b944823b1f20087e58112fb8d920f394979ecf5fd79d6cc7a49cc2`
- Cost-audit report SHA-256: `7d36f60a0a84b937df7f63ae8a66f40459a75e7714fb6775d54c0f4c7d95b4`
- Calibration artifact SHA-256: `08e88b4abe05dee0e8a8a1123b368e995e8a6a6f167487b222927734b7a041e5`
- Independent calibration-audit report SHA-256: `88d34dd5110babca6997efe26dc8dfdb88f5399834d351adfaf1592d70ba6dd0`
- Cost-audit script SHA-256: `fbf68f426659655de19a4e7e18705f3707406f5f45e52ae56023930953e96cfb`
- Calibration script SHA-256: `036705a042c523802139eddb3b587b0ff8a076444c43ab22da3e65e30a34c46a`
- Independent calibration-audit script SHA-256: `22f50889e00436e1b8865735c9d893854c4b9d6ef78fe04790453f8c54684aa1`

### Probability

- Independent walk-forward structural audit: **PASS** — 44 folds, 22,000 unique OOS validation events, 500 final-holdout predictions, no audit failures.
- Walk-forward OOS model: Brier **0.2489701**, log loss **0.6910857**.
- Walk-forward chronological baseline: Brier **0.2500046**, log loss **0.6931564**.
- Final holdout (500 events): model Brier **0.2421406**, log loss **0.6774056**; baseline Brier **0.2500087**, log loss **0.6931645**.
- A reproducible probability-skill audit uses a circular moving-block bootstrap over UTC days (1/3/5-day blocks; 5,000 replicates per length). On 22,000 walk-forward validation predictions, model-minus-baseline Brier delta was **−0.0010345** and log-loss delta **−0.0020707**; all three 95% block-bootstrap intervals were below zero. On the 500-event final holdout, Brier delta was **−0.0078681** and log-loss delta **−0.0157589**, but all 1/3/5-day block-bootstrap intervals included zero. The holdout improvement is therefore not statistically established.
- Raw reliability bins (21,974 causal-calibration OOS predictions) had 10,986 predictions in [0.4, 0.5) with mean predicted **0.4832** vs observed positive rate **0.4674**, and 10,988 in [0.5, 0.6) with mean predicted **0.5184** vs observed rate **0.5339**. The raw probability stream is tightly clustered around 0.5 and has limited resolution.
- The isotonic calibration produced extreme bins that were poorly supported: the [0.0, 0.1) bin had 132 predictions with observed positive rate **0.6061** despite mean calibrated probability **0.0769**; the [0.9, 1.0] bin had 131 predictions with observed positive rate **0.4046** despite mean calibrated probability **0.9231**. This is consistent with the degraded Brier/log-loss scores; calibrated outputs remain blocked.
- Probability skill audit SHA-256: `33c815de678ff2871e6fd5b6b7375ba802be1adf4c3e70eb36b62f9b894acfa8`.
- Causal isotonic calibration was independently audited against the current result SHA. It **degraded** the proper scores: raw Brier **0.2489784** → calibrated **0.2523406**; raw log loss **0.6911023** → calibrated **0.7020845**. The calibration artifact now explicitly reports `DEGRADED` and `BLOCK_CALIBRATED_PROBABILITIES`. Do not consume those calibrated probabilities downstream.

### Spread/slippage diagnostic

The new cost audit verifies the dataset SHA before calculation, uses observed entry/exit spread points, enters at the next M1 bar open, and exits at the source-defined realized endpoint. Slippage is stressed at 0/1/2/5/10 points per side.

- 24,850 source events; 24,826 had usable entry/exit bars; 24 skipped because next-bar entry was more than five minutes after the signal. The full-history event set yields 1,289 non-overlapping fixed-horizon events.
- Final holdout: 500 predictions; 498 had cost inputs; 2 were explicitly excluded and listed in the output. The non-overlapping final-holdout diagnostic contains **26 trades**.
- Compounded returns are deliberately omitted from overlapping-event diagnostics; overlapping event returns are not a valid portfolio equity curve.
- At 0 slippage points per side, signal mean return was **0.5691%** per event versus **0.1871%** for always-long on the same timestamps. Paired mean difference: **+38.19 bps**, bootstrap 95% interval **−6.13 to +107.69 bps**.
- At 10 slippage points per side, signal mean return was **0.5644%** versus **0.1824%** always-long; the paired interval still includes zero.
- At zero slippage, applying a generic **5 bps round-trip commission** reduced the final-holdout signal mean to **0.5191%** per trade; at **10 bps**, it was **0.4691%**. These holdout point estimates remain uncertain: the paired interval versus always-long stays **−6.13 to +107.69 bps** across the generic commission grid.
- The full report covers **25 combinations** (five slippage assumptions × five commission assumptions) and includes non-overlapping drawdown diagnostics. Commission assumptions are not broker-specific fees.
- The interval is a deterministic IID bootstrap and is **not adjusted for serial dependence**. Only 26 non-overlapping holdout trades are available. Broker commission, swap/financing, market impact, and measured live slippage are not included.

### Full-history directional baseline check

The economic result does not generalize cleanly from the final holdout to the full historical event set:

- Across **24,826 overlapping event diagnostics**, the signal averaged **−0.00444%** per event versus **+0.06161%** for always-long at zero assumed slippage; signal minus always-long was **−6.61 bps/event**. These overlapping returns are not a portfolio curve.
- Across **1,289 non-overlapping fixed-horizon events**, the signal averaged **+0.04438%** versus **+0.05028%** for always-long; signal minus always-long was **−0.59 bps/event**.
- At zero slippage, **5 bps round-trip commission** reduced the full-history signal mean to **−0.00562%** per event (always-long: **+0.00028%**); at **10 bps**, the signal mean was **−0.05562%** (always-long: **−0.04972%**). This sensitivity further fails to establish an economic edge; these are generic assumptions, not a broker fee quote.
- The final holdout's 26 non-overlapping events gave a positive point estimate (**+38.19 bps/event**) but the IID bootstrap 95% interval was **−6.13 to +107.69 bps**. It includes zero and does not account for temporal dependence.
- The 0/1/2/5/10-point slippage stress is paired with a separate 0/1/2/5/10-bps round-trip commission sensitivity. Commission bps are generic assumptions, not a broker-specific schedule; swap/financing, market impact, and measured live fills remain excluded. A complete net-execution edge is therefore not established.

**Trading edge: NOT PROVEN.** The final holdout point estimate is not enough: the interval includes zero, two holdout events lack cost inputs, the all-history signal underperforms the always-long baseline, and the calibrated probabilities worsen Brier and log loss. The cost audit now provides generic commission-bps sensitivity and drawdown diagnostics, but it still does not reproduce a broker's contract-specific commission schedule or include swaps, market impact, and measured fills. Do not enable the degraded calibration output or describe this strategy as profitable. The next valid economic test needs a pre-registered future holdout and broker-specific, commission-inclusive, non-overlapping portfolio accounting. Do not tune on the existing holdout.

### Verification and limitations

- Walk-forward structural audit: **PASS** — 44 folds, 22,000 unique OOS validation events, and 500 final-holdout predictions.
- Independent calibration audit: **PASS** for source/result binding and score reconstruction; calibration quality itself is **DEGRADED** (Brier 0.2489784 → 0.2523406; log loss 0.6911023 → 0.7020845).
- Focused probability-skill, calibration, walk-forward, and cost tests: **25 passed**. Targeted Ruff and format checks passed; targeted mypy returned `Success: no issues found in 1 source file` for the new probability-skill audit.
- GitHub CI at exact SHA `270d0ae92fd37c5749f180b6c201eb2b90e5bfee` completed successfully, including the C++ quant backend build, Python 3.11/3.12 tests, and full configured test suite with coverage: [CI run 38726553677](https://github.com/bi421/QROS/actions/runs/38726553677).
- A separate full local pytest run in the current Windows shell produced **4,233 passed, 3 failed, 90 errors, 79 skipped** because the C++ engine was not active in that test import context; C++ integration tests correctly refused to fall back to Python. This local run is **not** claimed as a pass. The exact-SHA GitHub CI run above is green.

CI green verifies code/test integration, not trading profitability. Probability-score uncertainty is now reported with 1/3/5-day temporal block-bootstrap diagnostics and reliability bins; the final-holdout intervals still include zero. Live measured execution costs and a commission-inclusive portfolio backtest remain unproven.
