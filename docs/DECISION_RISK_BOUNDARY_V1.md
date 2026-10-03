# ResearchOS Decision / Risk Boundary

**Status:** Superseded by `docs/RISK_MANAGEMENT_ARCHITECTURE_V2.md`
**Legacy sizing schema:** `risk.v1`
**Current governed schema:** `risk.v2`

The original boundary defined deterministic fractional-Kelly sizing from a validated
probability. That sizing contract remains readable for backward compatibility.

The production-facing risk boundary is now the governed V2 layer, which adds:

- immutable account/equity accounting;
- daily-loss and high-water-mark drawdown gates;
- strategy-loss and per-trade limits;
- portfolio open-risk and exposure limits;
- stale-data/session/permission/duplicate/order-rate/fat-finger controls;
- available-margin checks;
- explicit calibration and strategy-state gates;
- kill-switch state;
- immutable risk audit events;
- mandatory risk-context enforcement in the decision pipeline.

Canonical flow:

```
ProbabilityAssessment
      ↓
RiskInput (risk.v2)
      ↓
calculate_risk()
      ↓
RiskAccountSnapshot + RiskOrderIntent
      ↓
evaluate_risk_gate()
      ↓
RiskGateResult
      ↓
PreTradeReport + RiskAuditEvent
```

No broker connection, order placement, autonomous trading, or silent risk reduction
is implemented by this boundary.

See `docs/RISK_MANAGEMENT_ARCHITECTURE_V2.md` for the current contract and control set.
