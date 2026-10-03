# ResearchOS Risk Management Architecture V2

**Status:** Implemented / governed / research-only execution boundary
**Scope:** Account risk, strategy risk, portfolio risk, pre-trade controls, kill switch, audit lineage
**Schema:** `risk.v2`

## 1. Problem

ResearchOS previously had a fractional-Kelly sizing layer, but sizing alone is not risk management.

The missing controls were:

- account daily-loss accounting;
- high-water-mark drawdown accounting;
- strategy loss budget;
- maximum loss per trade;
- portfolio open-risk budget;
- gross exposure and single-instrument exposure;
- stale-data/session/permission/duplicate/order-rate/fat-finger controls;
- margin availability check;
- emergency kill switch;
- immutable risk audit events;
- governed strategy lifecycle;
- mandatory risk context at the decision-pipeline boundary.

## 2. Canonical flow

```
Validated Research Probability
        |
        v
RiskInput
        |
        v
calculate_risk()
        |
        v
RiskOrderIntent + RiskAccountSnapshot
        |
        v
evaluate_risk_gate()
        |
        +---- BLOCKED ----> immutable audit event
        |
        +---- PASS --------> human-review report
        |
        +---- PAPER/LIVE execution authorization flag
```

The risk layer never places an order or connects to a broker.

## 3. Policy

Default hard limits follow the repository's existing internal risk standard:

| Control | Default |
|---|---:|
| Target risk per trade | 0.25% equity |
| Maximum loss per trade | 0.50% equity |
| Maximum daily equity loss | 2.00% equity |
| Maximum total drawdown | 6.00% equity |
| Maximum strategy loss | 3.00% strategy reference |
| Maximum portfolio open risk | 1.00% equity |
| Maximum gross exposure | 3.0x equity |
| Maximum single-instrument exposure | 1.5x equity |
| Warning threshold | 80% of hard limit |

The existing Kelly sizing fields remain for backward compatibility. Hard governance checks are independent from sizing.

## 4. Account ledger

`RiskAccountSnapshot` is immutable and carries:

- current equity;
- day-start equity;
- high-water mark;
- strategy reference equity;
- strategy loss amount;
- current portfolio open risk;
- gross exposure;
- instrument exposure;
- realized P/L;
- unrealized P/L;
- trading costs;
- optional available margin;
- kill-switch state.

Equity must reconcile exactly, within a small numerical tolerance:

```
equity = day_start_equity
       + realized_pnl
       + unrealized_pnl
       - trading_costs
```

Daily loss and drawdown are computed from equity, not closed P/L alone.

## 5. Pre-trade hard gate

`RiskOrderIntent` carries the proposed execution context.

A gate failure never silently reduces or rewrites the proposed order.

Hard failures include:

- kill switch active;
- daily loss breached;
- total drawdown breached;
- strategy loss breached;
- maximum loss per trade breached;
- maximum portfolio open risk breached;
- maximum gross exposure breached;
- maximum single-instrument exposure breached;
- stale market data;
- closed session;
- symbol/strategy permission failure;
- duplicate order;
- order-rate limit breach;
- fat-finger price band breach;
- insufficient available margin;
- no positive risk budget;
- missing probability calibration for paper/live;
- strategy state not eligible for requested mode;
- missing position notional for executable intents.

## 6. Warnings

Warnings are emitted before hard limits are breached at 80% utilization.

Warnings never authorize a trade by themselves.

## 7. Kill switch

The kill switch is an account-level hard stop.

When active:

```
NO NEW EXECUTION
       |
       v
BLOCK
       |
       v
AUDIT EVENT
```

Automatic reset is not part of V2.

## 8. Strategy state machine

The governed lifecycle is:

```
RESEARCH
   ↓
VALIDATED
   ↓
RISK_REVIEW
   ↓
PAPER_ELIGIBLE
   ↓
DEPLOYMENT_ELIGIBLE
   ↓
ACTIVE
   ↓
SUSPENDED
   ↓
RETIRED
```

Suspension can return to `RISK_REVIEW`.

Transitions cannot skip required states.

## 9. Probability calibration

Paper/live execution modes require explicit:

```
probability_calibration_status == "Well-Calibrated"
```

The risk layer never infers this from probability magnitude, confidence, or another heuristic.

## 10. Decision-pipeline integration

The canonical `run_decision_pipeline()` now:

1. validates account-equity identity between pipeline input and risk snapshot;
2. converts the probability assessment into `RiskInput`;
3. calculates deterministic risk sizing;
4. constructs a governed `RiskOrderIntent`;
5. evaluates the complete hard-gate set;
6. creates an immutable content-addressed `RiskAuditEvent`;
7. returns a `PreTradeReport` carrying gate status, hard failures, warnings, and execution authorization state.

Missing risk-account context is a hard block.

## 11. Research-only boundary

`ExecutionMode.RESEARCH` can produce a risk calculation and review report, but `execution_allowed` remains false.

`PAPER` and `LIVE` are only risk-authorizable when their respective strategy lifecycle, calibration, account, portfolio, and operational gates pass.

No broker integration is implemented by this architecture.

## 12. Provenance

The following identities remain visible across the boundary:

- research/decision context id;
- model probability source;
- risk schema version;
- risk policy version;
- account snapshot;
- execution mode;
- strategy id;
- risk gate failures/warnings;
- immutable audit event id.

The risk layer does not convert a risk calculation into scientific evidence.

## 13. Next integration boundary

The next production-blocking work after V2 is persistence and operational wiring:

- durable account-risk ledger storage;
- broker/paper account state adapters;
- persistent kill-switch state;
- post-trade realized/unrealized P/L reconciliation;
- portfolio aggregation across positions;
- stress-test scenario engine;
- independent execution service boundary.

Until those are implemented, QROS remains a research/human-review system and does not claim live trading readiness.
