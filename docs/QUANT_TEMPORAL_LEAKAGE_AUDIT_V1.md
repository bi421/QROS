# Independent Temporal Leakage Audit v1

The audit checks a supplied train/validation/test split for strict chronological
ordering, realized label windows crossing the next partition boundary, missing
label-end timestamps, and feature-availability timestamps later than the event
timestamp. Missing partitions and malformed timestamp contracts are
fail-closed as invalid input; detected boundary violations are falsified.

A verified result is scoped to the records and timestamps supplied to the
audit. It does not prove that feature values were correctly constructed,
external data revisions were captured, hyperparameter selection avoided test
reuse, or the market strategy is profitable. Use actual feature availability
times and realized label end times, not approximations inferred from event time.

## Market Memory pipeline integration

The Market Memory pipeline runs this audit on its chronological train/validation/test
partitions using realized label-end timestamps. The resulting status and explanation
are attached to each evidence record and the report notes. A falsified boundary audit
rejects the report; invalid or unverifiable audit input prevents a validated status.
This is deliberately fail-closed and does not replace the walk-forward validator,
feature-provenance checks, or multiple-testing controls.
