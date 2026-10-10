# Independent Probability Calibration Audit v1

This audit independently recomputes probability validation reports from paired
probability assessments and observed outcomes. It checks multiclass Brier score,
log loss (including infinite loss when the realized class had zero probability),
expected and maximum calibration error, deterministic reliability bins, sample
counts, and the declared sample-size readiness gate.

The audit is opt-in and does not mutate the source assessment or report. A
verified report means its declared metrics are reproducible for the supplied
sample. It does not establish that forecasts are predictive, the sample is
independent or representative, there is no data leakage, or a trading strategy
is profitable. The raw outcomes and assessments must be the exact aligned
out-of-sample observations being audited.
