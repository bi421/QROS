# Profitability and Falsification Gate v1

**Status:** implemented as a pure evaluation primitive; not yet independently
validated against live or historical QROS market data.

## Purpose

QROS must test two competing outcomes: evidence that a strategy may be
profitable, and evidence that the profitability claim should be rejected.
A failed profitability gate is not automatically proof of unprofitability: the
system distinguishes negative evidence from insufficient evidence.

## Contract

Input consists of aligned, out-of-sample simple returns for the strategy and
a predeclared benchmark. Strategy returns must already reflect all declared
transaction costs, spread, slippage, and fees. The function does not estimate
or invent costs. It rejects unaligned series and undeclared costs.

**Important trust boundary:** `costs_included=True` is a caller assertion, not
proof that costs were actually deducted. Before production integration, the
caller must bind the returns to a versioned cost model and an auditable source
artifact (including its hash). A report must not convert the boolean alone
into a verified-cost claim.

The evaluator reports:
- sample count and arithmetic mean net return;
- moving-block-bootstrap confidence intervals for net and benchmark-relative
  mean returns;
- realized maximum drawdown on the supplied net return series;
- exact verdict and human-readable reasons.

The moving-block bootstrap uses a deterministic seed and circular blocks to
preserve some short-range serial dependence. It is not a universal solution
for regime changes, long memory, or dependence across overlapping labels.
Choose the block length before inspecting the final result and record it in
the research plan.

## Verdicts

| Verdict | Meaning |
| --- | --- |
| `SUPPORTED_IN_SAMPLE` | Both lower confidence bounds are above zero and the drawdown cap passes. Evidence is limited to this sample and declared assumptions. |
| `NOT_PROFITABLE` | The upper confidence bound for net mean return is at or below zero. |
| `NO_BENCHMARK_EDGE` | The upper confidence bound for benchmark-relative mean return is at or below zero. This does not necessarily mean absolute returns are negative. |
| `RISK_LIMIT_BREACH` | Observed drawdown exceeds the predeclared maximum; the risk gate overrides a positive mean. |
| `INCONCLUSIVE` | Sample is too small or one or more intervals include zero. Do not market this as a pass or as proof of no edge. |
| `INVALID_EVIDENCE` | Inputs are malformed/misaligned or costs are not declared included. Fail closed. |

## What this does not prove

This primitive is one gate, not a full trading certification. A supported
in-sample result does not establish live profitability, causal explanation,
execution quality, or future persistence. Release of a profitability claim
also requires, at minimum:

1. a frozen hypothesis, benchmark, event horizon, cost model and stopping rule;
2. verified point-in-time data and no look-ahead or label leakage;
3. chronological out-of-sample / walk-forward evaluation;
4. multiple-testing and selection-bias controls;
5. negative controls (including label shuffling where appropriate);
6. regime and parameter sensitivity checks;
7. independent replication on a distinct holdout or period;
8. reproducible source data, code SHA, parameters, seed, and output hashes.

Do not interpret a negative result as a command to tune until it passes. If
the hypothesis is changed after seeing results, create a new version and use
fresh holdout evidence. Report the full verdict distribution, including
rejected and inconclusive experiments.

## Initial acceptance checks

Regression tests cover:
- positive net and benchmark-relative evidence;
- negative net evidence;
- positive returns without benchmark edge;
- absent cost declaration;
- misaligned benchmark data;
- uncertainty crossing zero;
- drawdown overriding apparent profitability.

These tests prove only the evaluator's programmed decision rules. They do
not establish any edge for XAUUSD or any other instrument.
