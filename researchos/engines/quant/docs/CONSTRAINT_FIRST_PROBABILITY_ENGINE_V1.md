# Constraint-first empirical probability kernel v1

## Purpose

Scan one chronological close-price array in native C++20, then evaluate a bounded
set of candidate hypotheses using empirical forward close-to-close returns.
The initial contract targets up to 1,000,000 candles and 100,000 candidate rows,
with no more than 64 distinct horizons per call.

Each candidate consists of:
- target_bps: positive forward return threshold in basis points;
- horizon: forward bars (5 compares close[i + 5] with close[i]);
- direction: +1 long-direction threshold or -1 short-direction threshold.

For each unique horizon, the engine computes and sorts the historical forward
returns once. Each candidate then uses binary search, rather than rescanning all
candles. Complexity is approximately O(H * N log N + C log N), where H is the
number of distinct horizons (bounded to 64), N is candle count, and C is
candidate count. Benchmark on the target machine before claiming a speed target.

## Important statistical boundary

The returned rate is the fraction of historical forward close-to-close returns
that met the candidate's target threshold. It does not mean the price touched
a take-profit before a stop-loss, and it does not account for spread, commission,
slippage, funding, or execution constraints. Forward samples overlap and are
dependent. The rate is exploratory, not a calibrated probability of future
profit. Use chronological holdout periods, costs, multiple-testing correction,
and block-based uncertainty estimates before ranking or acting on candidates.

The engine rejects non-finite/non-positive closes, invalid candidate directions,
invalid targets/horizons, mismatched arrays, and candidate sets with too many
unique horizons. It does not silently truncate, impute, or repair inputs.

## Build and use

Build the repository's existing CMake/nanobind package, then call
researchos.engines.quant.python.cpp_quant_engine.constraint_first.evaluate_candidates
with contiguous NumPy arrays. The close-price input is passed to C++ without a
data copy; non-contiguous inputs are normalized by the Python facade.

A benchmark must report the exact commit, Python/C++ versions, CPU, candle and
candidate counts, unique horizons, wall time, and memory. No performance claim
is accepted until measured.
