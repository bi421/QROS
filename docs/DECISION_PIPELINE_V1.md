# Decision Pipeline V1

## Purpose

This document defines the canonical ResearchOS boundary from validated research probability to a human-review pre-trade report.

```text
Block 2: ProbabilityAssessment
          |
          | risk_input_from_probability()
          v
Block 3: RiskInput -> calculate_risk()
          |
          v
Block 4: PreTradeReport
          |
          v
     Human review only
```

## Invariants

1. Block 2 owns research evidence and probability.
2. Block 3 owns risk mathematics and explicit policy caps.
3. Block 4 owns presentation/report assembly only.
4. Neutral probability is never silently converted into a trade direction.
5. No block places orders, talks to a broker, or performs autonomous execution.
6. The legacy boundary is versioned (`risk.v1`, `pretrade.v1`); the current governed contracts are `risk.v2` and `pretrade.v2`.
7. A serialized Block 2 assessment is accepted so implementations can cross a language/process boundary.

## Canonical entry point

`run_decision_pipeline(DecisionPipelineInput)` executes the complete deterministic path.

The caller must explicitly provide:

- selected direction (`bullish` or `bearish`)
- account equity
- historical average win/loss
- research validation status
- optional risk-per-unit
- optional risk policy

The pipeline returns `PreTradeReport`; it does not return an order instruction.
