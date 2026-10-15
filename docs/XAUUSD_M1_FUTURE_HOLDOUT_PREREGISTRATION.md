# XAUUSD M1 Future Holdout Pre-registration Protocol

**Status:** protocol only; no future holdout is certified or evaluated by this document.  
**Created:** 2026-10-15  
**Research boundary:** QROS produces research evidence and does not execute orders.

## Purpose

The existing final holdout has only 26 non-overlapping 1-day events and its paired-return confidence interval includes zero. It has already been inspected. It must not be reused for model selection, calibration fitting, threshold tuning, feature selection, or a new confirmatory claim.

This protocol defines the next prospective evaluation before its data are inspected. It is intended to reduce hindsight bias and prevent a favorable point estimate from being described as a proven trading edge.

## Freeze record — required before the first holdout event

Create a version-controlled, timestamped registration record containing:

- Git commit SHA and hashes of the model, configuration, feature schema, signal rules, calibration artifact (or explicit statement that calibration is disabled), data parser, and evaluation code.
- Exact instrument and venue/feed, timezone, timeframe, event definition, signal timing, entry timing, exit timing, and maximum permitted data gap.
- Start and end timestamps for the prospective period, chosen before outcomes are available. No start date may be moved after inspecting results.
- Primary outcome, primary benchmark, statistical procedure, confidence level, multiple-testing policy, cost schedule, and minimum sample/power analysis.
- All exclusions, missing-data rules, tie handling, and invalid-event handling.
- A SHA-256 hash of the signed-off registration record, committed before the prospective evaluation begins.

Any change after registration creates a new protocol version and a new future holdout. Do not silently replace the original protocol.

## Evaluation data and leakage controls

1. Use only events timestamped after the registration commit and after all model choices are frozen.
2. Fit any scaler, feature selection, probability calibration, threshold, or hyperparameter using training data only. If the production model has no valid causal training procedure, disable the component rather than fitting it on the holdout.
3. Enforce time-ordered splits and purge/embargo overlapping outcome windows between training, validation, and holdout.
4. Bind source events, raw dataset, generated predictions, costs, and report to SHA-256 hashes. Fail closed on identity mismatch, duplicate IDs, non-monotonic timestamps, non-finite values, or missing required cost fields.
5. Do not select only favorable sessions, directions, volatility regimes, or events after outcomes are known. Report all registered exclusions and their counts.
6. Preserve the original holdout output even if the result is negative. A rerun with modified rules is exploratory, not a replacement confirmatory test.

## Minimum evidence before making a decision

Before the holdout starts, run and record a power/sample-size analysis based on a predeclared economically meaningful net-return improvement and conservative dependence assumptions. The evaluation is **inconclusive** if the registered minimum sample is not reached. Do not claim significance from a large number of overlapping predictions when the independent non-overlapping trade count is small.

Use non-overlapping portfolio events for primary economic inference. Event-level overlapping returns may be reported only as a secondary diagnostic.

## Primary economic endpoint

The primary endpoint is the difference in mean **net** return per non-overlapping event between the frozen signal and a pre-registered benchmark, after the same execution and cost assumptions are applied to both.

Before the holdout starts, select and document:
- The primary benchmark (at minimum, a no-trade/cash baseline and a fixed directional baseline appropriate to the registered strategy).
- A broker-specific spread and commission schedule, swap/financing treatment where applicable, and slippage assumptions grounded in measured data where available.
- Position sizing, exposure limits, capital allocation, compounding assumptions, and treatment of margin and rejected/partial fills.

If broker-specific costs or realistic fill data are unavailable, label the result a sensitivity analysis and **do not** certify net tradability.

### Statistical decision rule

- Compute paired signal-minus-benchmark returns on the exact same eligible timestamps.
- Use a moving-block bootstrap over calendar/trading days to preserve serial dependence. Pre-register the block-length selection rule and number of resamples; report the interval and seed.
- The primary endpoint passes only if the two-sided 95% confidence interval's lower bound is strictly greater than zero under the registered realistic cost model, the minimum sample/power criterion is met, and all data-integrity checks pass.
- Report 1-, 3-, and 5-day block sensitivity as secondary robustness checks. If the registered primary procedure fails, do not choose whichever secondary interval looks best.
- Report net mean and median return, win rate, profit factor, compounded return, maximum drawdown, exposure, trade count, and the full cost assumptions. A positive mean alone is insufficient.
- Report adverse/failure scenarios and all registered benchmarks, not only the best comparison.

This is a predeclared decision rule, not a guarantee that the strategy will pass.

## Probability quality endpoint

If the model emits probabilities, evaluate the untouched future holdout against a training-only base-rate baseline.

- Primary probability metrics: Brier score and log loss.
- Compare model-minus-baseline differences using a time-block bootstrap; lower values are better, so an improvement requires the upper confidence bound for each registered primary difference to be below zero.
- Report reliability diagrams/tables with bin counts, mean predicted probability, and observed frequency. Include calibration intercept/slope and uncertainty where sample size supports them.
- Expected calibration error is descriptive only and must not be the sole calibration criterion.
- If calibration is fitted, it must be fit on training/validation data only. Do not refit or tune calibration on the final holdout.
- A probability-skill pass does not imply economic edge; an economic-edge pass does not automatically imply calibrated probabilities.

## Multiple comparisons and reporting

Register one primary economic endpoint and one primary probability endpoint before testing. Treat all additional horizons, indicators, subgroups, thresholds, cost scenarios, and model variants as secondary/exploratory. Apply a predeclared multiplicity correction if inferential claims are made across multiple secondary tests.

Publish the machine-readable result artifact with:
- protocol hash and frozen commit SHA;
- dataset/source/prediction/cost artifact hashes;
- exact sample counts and all exclusion reasons;
- baseline definitions;
- point estimates, confidence intervals, bootstrap settings, and cost schedule;
- calibration tables and proper scores, when probabilities are available;
- software/runtime versions and reproducible command;
- explicit status: `PASS`, `FAIL`, or `INCONCLUSIVE`.

Never convert `INCONCLUSIVE` to `PASS` based on a favorable point estimate.

## Current status

**Trading edge: NOT PROVEN.** This protocol is not itself test evidence. The previously inspected holdout is not eligible for another confirmatory claim. A future prospective holdout must be frozen, collected, and evaluated under this protocol before any edge certification is considered.
