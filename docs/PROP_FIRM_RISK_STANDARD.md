# ResearchOS — Global Prop-Firm Risk Standard v1.0

**Status:** Mandatory research/deployment-readiness standard  
**Scope:** ResearchOS strategy research, evidence certification, risk evaluation, and future execution controls  
**Principle:** No strategy may graduate from research into deployment eligibility unless every applicable hard gate passes.

> This standard is an internal conservative benchmark inspired by institutional market-risk controls, exchange risk controls, and published proprietary-trading evaluation rules. It is **not** a claim that every proprietary firm uses these exact percentages.

## 1. Non-negotiable hierarchy

The system must enforce this order:

`DATA INTEGRITY → MODEL VALIDITY → OOS EVIDENCE → RISK LIMITS → EXECUTION SAFETY → DEPLOYMENT`

A failure at any earlier layer blocks all later layers.

**Never:**
- convert an in-sample result into a production claim;
- treat a positive backtest as permission to trade;
- relax a failed gate to obtain a passing result;
- fill, interpolate, repair, or silently resample missing market observations;
- use future information in feature construction, calibration, or decision rules;
- report a probability without out-of-sample evidence and calibration status.

## 2. Account-level hard risk limits

ResearchOS must support configurable account-level limits. Conservative default profile:

| Control | Default hard limit | Action |
|---|---:|---|
| Maximum daily equity loss | 2.0% | HARD BLOCK / flatten |
| Maximum total drawdown | 6.0% | HARD BLOCK |
| Maximum loss per strategy | 3.0% | HARD BLOCK |
| Maximum loss per trade | 0.50% | HARD BLOCK |
| Default target risk per trade | 0.25% | DEFAULT |
| Maximum portfolio open risk | 1.00% | HARD BLOCK |
| Maximum gross exposure | 3.0x equity | HARD BLOCK |
| Maximum single-instrument exposure | 1.5x equity | HARD BLOCK |

Limits are calculated from **equity**, including floating P/L, commissions, swaps/financing, and other explicitly modeled trading costs.

The implementation must distinguish:
- soft warning thresholds;
- hard violation thresholds;
- recovery/reset rules;
- emergency kill state.

## 3. Position sizing

Position size must be derived from risk, not from the maximum broker/exchange margin allowed.

Required calculation concept:

`position_size = allowed_trade_risk / stop_distance_cost`

The sizing engine must account for:
- stop distance;
- contract/tick value;
- spread;
- expected slippage;
- commissions;
- financing where applicable;
- currency conversion;
- current portfolio exposure;
- correlated exposure.

No position may be opened when the resulting worst-case modeled loss breaches an account or portfolio hard limit.

## 4. Pre-trade controls

Every future execution path must support, at minimum:

- maximum order size;
- maximum position size;
- maximum message/order rate;
- maximum execution rate;
- price-band / fat-finger checks;
- available-risk check;
- margin check;
- duplicate-order detection;
- stale-price/data-age check;
- market-open/session check;
- symbol permission check;
- strategy permission check;
- portfolio exposure check;
- correlation/concentration check;
- emergency kill switch.

A failed pre-trade check means **NO ORDER**.

## 5. Daily loss and drawdown accounting

Daily loss must be based on equity, not closed P/L alone.

The daily risk ledger must include:
- realized P/L;
- unrealized P/L;
- commissions;
- swaps/financing;
- execution costs;
- rejected/cancelled order counts where operationally relevant.

Drawdown must be tracked from the configured reference point (initial equity, high-water mark, or strategy-specific reference) and the exact rule must be immutable for each evaluation run.

## 6. Stress testing

Every strategy that reaches deployment review must survive at least:

1. spread expansion;
2. slippage expansion;
3. gap/open-jump scenarios;
4. volatility shock;
5. liquidity reduction;
6. delayed execution;
7. missing/stale macro data;
8. market-session boundary conditions;
9. consecutive-loss sequences;
10. correlation shock for multi-factor/multi-position portfolios.

The base case is insufficient. A strategy must demonstrate survivability under **extreme but plausible** conditions.

## 7. Market-data integrity gates

A strategy is BLOCKED if any critical data condition fails:

- duplicate timestamps;
- non-monotonic timestamps;
- unexplained gaps;
- timestamp timezone ambiguity;
- symbol mismatch;
- stale observations;
- inconsistent OHLC relationships;
- corrupted values;
- unexplained source changes;
- hidden forward filling/interpolation;
- look-ahead contamination;
- unverifiable source identity/hash.

Every production dataset must have immutable source identity and SHA-256 provenance.

## 8. Research and statistical evidence gates

A strategy must not graduate based on one backtest metric.

Required evidence where applicable:

- chronological train/validation/test separation;
- walk-forward out-of-sample evaluation;
- comparison against a clearly defined baseline;
- confidence intervals or equivalent uncertainty quantification;
- statistical significance appropriate to the experiment;
- multiple-testing awareness when many variants are searched;
- stability across time/regimes;
- sensitivity to reasonable cost assumptions;
- calibration assessment for probabilistic outputs;
- minimum effective sample size.

The canonical Phase52 gate remains mandatory. If its dataset gate is `BLOCKED`, predictive conclusions remain `BLOCKED`.

## 9. Probability and model-risk rules

A probability is not a trading instruction merely because a model emitted it.

A probability may be exposed as a decision-grade probability only when:

1. the model was evaluated out-of-sample;
2. calibration was evaluated out-of-sample;
3. baseline comparison is available;
4. sample sufficiency passes;
5. feature/data provenance is complete;
6. the result survives configured risk/cost stress tests.

Otherwise the output must be explicitly labeled:

`RESEARCH ONLY — NOT DEPLOYMENT ELIGIBLE`

## 10. Kill-switch requirements

Future live/paper execution components must provide an independent emergency stop that can:

- stop new orders immediately;
- cancel working orders where supported;
- optionally flatten positions according to configured policy;
- persist the reason for activation;
- prevent automatic restart until an explicit reset;
- create an immutable audit event.

Kill-switch activation must be possible for:
- daily loss breach;
- maximum drawdown breach;
- abnormal order rate;
- stale/invalid market data;
- strategy integrity failure;
- connectivity failure;
- unexpected model/version mismatch;
- operator emergency.

## 11. Operational controls

Every deployment candidate must have:

- immutable strategy/version identity;
- immutable configuration identity;
- dataset identity/hash;
- model artifact identity/hash;
- risk-profile identity;
- execution environment identity;
- complete decision/order audit trail;
- deterministic or reproducible evaluation where applicable;
- rollback procedure;
- incident classification and post-incident review.

No silent configuration changes are allowed.

## 12. Strategy state machine

A strategy must move only through these states:

`RESEARCH → VALIDATED → RISK_REVIEW → PAPER_ELIGIBLE → DEPLOYMENT_ELIGIBLE → ACTIVE → SUSPENDED → RETIRED`

Rules:

- `RESEARCH`: evidence incomplete or exploratory.
- `VALIDATED`: scientific evidence gates pass.
- `RISK_REVIEW`: risk and stress tests are being evaluated.
- `PAPER_ELIGIBLE`: risk controls pass but live capital is not authorized.
- `DEPLOYMENT_ELIGIBLE`: all mandatory controls pass.
- `ACTIVE`: explicitly authorized and monitored.
- `SUSPENDED`: a hard condition requires trading to stop.
- `RETIRED`: strategy is permanently removed from active consideration.

A strategy cannot skip states.

## 13. Violation policy

Hard violations must be fail-closed.

Required behavior:

`VIOLATION → BLOCK → AUDIT EVENT → HUMAN REVIEW → EXPLICIT RESET`

No automatic relaxation of limits is permitted after a violation.

Repeated violations must increase the severity classification and may permanently suspend the strategy.

## 14. ResearchOS implementation priority

### P0 — mandatory before any deployment claim

- risk-policy contract;
- daily-loss/equity accounting;
- max-drawdown accounting;
- per-trade and portfolio risk budget;
- pre-trade validation contract;
- stress-test framework;
- kill-switch state model;
- immutable audit events;
- strategy state machine;
- hard integration with Phase52 evidence gates.

### P1 — mandatory before serious paper-trading

- slippage/spread scenario engine;
- gap/volatility stress suite;
- exposure/correlation limits;
- model/version compatibility checks;
- operational health monitoring;
- incident/recovery workflow.

### P2 — institutional hardening

- independent risk-service boundary;
- multi-account aggregation;
- real-time risk dashboards;
- limit utilization alerts;
- automated post-trade surveillance;
- model drift/degradation detection;
- immutable compliance/audit export.

## 15. Current ResearchOS consequence

The existing Phase52 production dataset currently has 1,181 usable observations against a required 1,200. Therefore the scientific gate remains **BLOCKED**.

Under this standard, that means:

`NO PREDICTIVE DEPLOYMENT CLAIM`

`NO LIVE-TRADING ELIGIBILITY`

`NO PROBABILITY-BASED EXECUTION AUTHORIZATION`

This is intentional. A professional risk system should prefer **NO TRADE / NO CLAIM** over an unsupported signal.

## 16. Reference basis

This standard is informed by published controls from:

- CFTC automated-trading risk-control guidance: pre-trade maximum order size, message/execution controls, and emergency disengagement/kill-switch concepts.
- CME risk-management materials: risk limits, position sizing based on risk scenarios, stress testing, position limits, and pre/post-trade controls.
- Published FTMO trading objectives: equity-based maximum daily loss and maximum loss rules.

These references establish the control categories and philosophy. ResearchOS's numerical defaults are intentionally conservative internal defaults and remain configurable by risk profile.


## 17. Executable Risk Management V2 — 2026-10-03

The P0 risk-management boundary is now implemented in code under:

```
researchos/risk/
```

Implemented:

- versioned `RiskPolicy`;
- immutable account/equity risk snapshot;
- daily-loss, total-drawdown, and strategy-loss accounting;
- maximum loss per trade;
- portfolio open-risk budget;
- gross and single-instrument exposure limits;
- stale-data, session, permission, duplicate-order, order-rate, fat-finger, and margin gates;
- explicit paper/live calibration and strategy-state gates;
- kill-switch state;
- immutable content-addressed risk audit events;
- governed strategy state machine;
- mandatory risk-context enforcement in `run_decision_pipeline()`;
- risk status, hard failures, warnings, and audit event in `PreTradeReport`.

The implementation remains research/paper/live-risk **authorization logic only**. It does not place broker orders.

The remaining operational layer is persistence and real account-state adapters. Until those exist, a green risk calculation is not evidence of live execution readiness.
