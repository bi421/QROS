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
