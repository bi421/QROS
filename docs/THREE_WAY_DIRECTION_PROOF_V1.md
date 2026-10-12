# Three-way direction proof contract

## Purpose

The canonical Decision Engine now emits exactly one direction label for each
validated probability assessment: `UP`, `DOWN`, or `NEUTRAL`. The label is
accompanied by a machine-verifiable proof artifact.

## Formula

For each evidence item (i), the existing weighted-evidence formula is:

`contribution_i = confidence_i * weight_i`

For class (c):

`S_c = sum(contribution_i for items whose direction is c)`

If `S_UP + S_DOWN + S_NEUTRAL > 0`:

`P(c) = S_c / (S_UP + S_DOWN + S_NEUTRAL)`

If every contribution is zero, the defined fallback is a uniform distribution
(`1/3` for each class). The NEUTRAL probability is set to the residual after
UP and DOWN to preserve the canonical calculator's normalization rule.

The label is the class with the greatest probability. If multiple classes tie
for the maximum within the declared numerical tolerance, the result is
`NEUTRAL`. This tie rule is deterministic and is part of the contract.

## What the proof checks

- Exact three-way direction vocabulary and finite inputs.
- Evidence source SHA-256, calculated from the canonical embedded evidence.
- Independent recomputation of class contributions and probabilities.
- Probability bounds and sum-to-one invariant.
- Decision label agrees with the maximum-probability rule.
- Proof SHA-256 matches the complete payload.
- The canonical `DecisionPipeline` emits the proof and fails closed if the
  proof probabilities differ from its `ProbabilityAssessment`.

## Scope and limitations

This proof establishes that the supplied evidence was aggregated according to
the declared formula and that the three-way output follows from those
calculations. It does not establish that upstream evidence itself describes
reality, that probabilities are empirically calibrated, or that any future
market outcome is guaranteed. Calibration and data-source validity require
their own evidence artifacts. This is a research-only output and never places
orders or executes trades.
