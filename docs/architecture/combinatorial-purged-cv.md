# QROS combinatorial purged cross-validation

## Scope

The `combinatorial_purged_cv.py` module adds CPCV-style combinatorial test splits for labelled XAUUSD research events. It is a classifier-validation diagnostic, not an economic backtest and not trade execution.

For `n_groups=6, n_test_groups=2`, all 15 test-group combinations are evaluated. Every report stores the exact zero-based row indices and event IDs for train, test, purged and embargoed sets, plus reasons for each purge/embargo removal. Each split stores model status and holdout metrics; aggregate mean, median, minimum and maximum are reported alongside the prevalence baseline.

## Purge and embargo policy

- Every row requires ISO-8601 `timestamp` and `label_end_timestamp`. `event_id` is optional but must be unique when supplied.
- Source rows must already be strictly chronological. The module rejects duplicates/out-of-order input rather than silently sorting it.
- For each split, a candidate train event is purged if its inclusive interval `[timestamp, label_end_timestamp]` intersects any test event interval. Boundary contact counts as overlap.
- An otherwise eligible train event is embargoed if its start time is strictly after a test block's latest label end and at or before that time plus the configured embargo duration.
- `purged_indices_zero_based`, `embargo_indices_zero_based`, event IDs and reason maps identify exactly what was removed for every split.
- The report records dataset SHA-256, current Git HEAD, validation source SHA-256, canonical config SHA-256 and a deterministic result SHA-256. The full report includes a generation timestamp, so compare `deterministic_result_sha256` when reproducing results.

## Run

Input is UTF-8 JSON containing either an array of event objects or an object with a `rows` array. Each row needs the five logistic features (`z_speed`, `body_ratio`, `upper_wick_ratio`, `lower_wick_ratio`, `h1_aligned`), a binary `label` and timestamps.

```powershell
Set-Location "C:\Users\User\Desktop\QROS"
python scripts\run_combinatorial_purged_cv.py `
  --input .\artifacts\labelled_xauusd_events.json `
  --output .\artifacts\cpcv_audit.json `
  --groups 6 `
  --test-groups 2 `
  --embargo-minutes 60 `
  --min-train-rows 100 `
  --l2 1.0
```

The output path is created if needed; the input dataset is never overwritten. Exit code 0 means at least one valid split completed, not that an edge was established.

## Interpretation limitations

- These are combinatorial purged CV **splits**; this module does not yet stitch complementary splits into canonical CPCV backtest paths. Do not label its split count as path count.
- Fold scores are dependent because training sets overlap. Their distribution is a stability diagnostic, not a confidence interval from independent trials.
- `label_end_timestamp` must reflect the full future horizon used to produce each label. Incorrect event end-times make purging invalid.
- The embargo is specified in elapsed time, not number of bars. Set it from the feature/label dependency horizon before inspecting test results.
- This module does not automatically calculate PnL, costs, capacity, multiple-testing-adjusted strategy profitability, or an untouched final 2025 holdout.
- Never use the best split as the reported result. Retain the entire report and all attempted configurations in the experiment ledger.
