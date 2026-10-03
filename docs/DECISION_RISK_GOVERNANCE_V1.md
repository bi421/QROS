# QROS Decision Risk Governance V1

**Status:** Implemented — awaiting exact-head CI  
**Scope:** Account and portfolio risk controls around the existing risk.v1 sizing layer  
**Principle:** fail closed; research-only; no broker/order execution

## Why this layer exists

QROS already had a deterministic per-trade sizing calculation:

`probability -> Kelly/fractional-Kelly -> max risk cap -> position size`

That is sizing, not complete risk management.

This layer adds the missing control plane around that calculation:

`research validation -> risk sizing -> account state -> hard risk limits -> pre-trade risk decision -> human review`

## Hard controls

The default profile is aligned with the repository risk standard:

| Control | Default |
|---|---:|
| Maximum daily equity loss | 2.0% |
| Maximum total drawdown | 6.0% |
| Maximum loss per strategy | 3.0% |
| Maximum loss per trade | 0.50% |
| Target trade risk | 0.25% |
| Maximum portfolio open risk | 1.00% |
| Maximum gross exposure | 3.0x equity |
| Maximum single-instrument exposure | 1.5x equity |

These are internal configurable defaults, not broker or proprietary-firm guarantees.

## Account-state model

Every governance evaluation consumes an immutable account snapshot containing:

- day-start equity;
- current equity;
- high-water-mark equity;
- strategy reference equity;
- strategy P/L;
- currently open risk;
- current gross exposure;
- current single-instrument exposure;
- emergency kill-switch state and reason.

Daily loss and drawdown are equity-based. The caller is responsible for supplying
an equity snapshot that reflects floating P/L and explicitly modeled costs.

## Pre-trade gate

For one proposed trade, QROS calculates:

- current daily loss fraction;
- current drawdown fraction;
- current strategy loss fraction;
- proposed trade risk fraction;
- projected portfolio open-risk fraction;
- projected gross exposure fraction;
- projected single-instrument exposure fraction.

A hard violation yields:

`status = BLOCKED`

and an immutable machine-readable violation record.

No automatic limit relaxation or alternative trade is selected.

## Fail-closed conditions

The gate blocks when:

- research validation is false;
- strategy state is not eligible for risk review;
- the emergency kill switch is active;
- proposed notional is missing;
- risk sizing was calculated from a different current-equity snapshot;
- any hard account, strategy, portfolio, or concentration limit is reached.

Near-limit utilization is emitted as a warning without overriding the hard gate.

## Strategy state machine

The risk/deployment lifecycle is:

`RESEARCH -> VALIDATED -> RISK_REVIEW -> PAPER_ELIGIBLE -> DEPLOYMENT_ELIGIBLE -> ACTIVE -> SUSPENDED -> RETIRED`

Suspended strategies may return only to RISK_REVIEW or retire. States may not be skipped.

The implementation validates adjacent transitions and uses the state as a pre-trade gate.

## Immutable risk audit

Each evaluation returns a `RiskDecision` with a deterministic SHA-256 audit hash
over the decision inputs/outputs represented by the result.

The hash is content-derived rather than timestamp-derived, so identical risk
conditions produce the same audit identity.

## Main-system integration

The canonical decision path is now:

`ProbabilityAssessment`

`-> RiskInput / calculate_risk()`

`-> RiskAccountState + RiskLimits + proposed_notional`

`-> evaluate_pretrade_risk()`

`-> PreTradeReport`

The pre-trade report cannot be `READY_FOR_HUMAN_REVIEW` unless the risk governance
decision passes.

This is still not an order authorization. Broker execution, message-rate
controls, price bands, margin checks, and kill-switch actuation remain outside
the research-only package and belong to a future execution service.

## Explicit boundary

This implementation intentionally does not invent:

- portfolio correlation without explicit portfolio factor inputs;
- spread/slippage assumptions without caller-supplied costs;
- margin availability;
- live market-data freshness;
- broker/exchange permissions;
- execution behavior.

Those controls require additional observed inputs and should be added only with
contracts that can carry real evidence.

## Verification target

The implementation is accepted only after:

1. focused risk-governance tests pass;
2. decision-pipeline regression tests pass;
3. ruff passes;
4. mypy passes;
5. full CI passes at the exact PR head SHA;
6. Release Readiness, Supabase security, Supply Chain, and post-merge gates pass;
7. the resulting main SHA is re-verified.

## Result

Risk management is no longer an isolated Kelly-sizing calculation. The research
decision pipeline now contains a hard account/portfolio risk-governance boundary
that can block a nominally valid research result before it becomes human-review
ready.
