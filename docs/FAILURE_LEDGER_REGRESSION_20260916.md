# Failure Ledger — Regression Verification Audit

**Date:** 2026-09-16  
**Scope:** ResearchOS scientific/regression verification only  
**Status:** OPEN — no Bayesian engine or new hypothesis work permitted until these verification gaps are resolved.

This ledger records concrete regression blind spots found in repository evidence. A test-count/CI badge is not treated as proof of numeric correctness.

| # | Finding | Evidence | Risk | Required verification | Status |
|---|---|---|---|---|---|
| 1 | **Percentage-return scaling contract is regression-sensitive.** A historical C++ regression test multiplied `winrate` and `total_return` by 100 even though the API values were already percentages; this was fixed in commit `28d7a4e`. | Commit `28d7a4e` explicitly fixes the double-`*100` bug in `test_cpp_backtest_regression.py`. | HIGH — a factor-100 error can make a numerically wrong result look plausible or make a valid result fail a range test. | Keep an explicit unit contract test for every percentage-return field and assert both representation and numeric value against an independent reference. | OPEN |
| 2 | **C++ backend availability can be hidden by fallback architecture.** ResearchOS has a Python fallback boundary, so generic Python tests can pass without exercising compiled C++ numerics. | Current C++ regression fixture explicitly fails when `CppQuantAdapter.is_cpp` is false. | HIGH — a green Python suite is not equivalent to C++ numeric verification. | Run a dedicated compiled-backend regression job and require the test to execute with `is_cpp == True`. | OPEN |
| 3 | **The canonical pytest configuration historically excluded the C++ backtest regression test.** Current `pyproject.toml` contains `--ignore=researchos/tests/test_cpp_backtest_regression.py`. | `pyproject.toml` main branch `tool.pytest.ini_options.addopts`. | HIGH — the test can exist and remain green while never being collected by the normal suite. | Remove the test-file ignore and obtain a real PASS/FAIL result in an environment where the C++ backend and required data are available. | OPEN |
| 4 | **Backtest numeric correctness is not fully asserted by the current regression test.** The test independently calculates winrate/total return in Python, but the C++ `statistics`/`metrics` objects are only asserted to be non-empty; the independently calculated numeric values are not compared against the C++ metric fields. | `researchos/tests/test_cpp_backtest_regression.py`: `run_cpp_metrics()` asserts only truthiness of `statistics`/`metrics`; `test_sma_20_50_winrate()` and `test_sma_20_50_total_return_range()` validate the Python reference values/ranges. | CRITICAL — a C++ metric could be numerically wrong while the test still passes, provided the result dictionaries are non-empty. | Add exact field-level parity assertions with tolerances against an independently computed reference, including win rate, total return, drawdown, trade count and any exposed return-series fields. | OPEN |
| 5 | **The regression test is data-dependent on `data/raw/histdata/xauusd`, so collection/execution status can differ from a data-complete environment.** It fails closed if the directory or XAUUSD M1 CSVs are absent. | Current `load_xauusd_1d()` calls `pytest.fail()` when the directory/files are absent. | HIGH — CI can report a failure unrelated to the numerical implementation, while local data can hide the same environmental dependency. | Make the regression fixture's data source explicit and deterministic for CI, or run it in a dedicated data-complete job; never convert missing required scientific data into a skip. | OPEN |
| 6 | **CI coverage can have verification blind spots beyond the headline Python test count.** The architecture forensic audit documented package-local test roots omitted from CI, C++ `ctest || echo` failure masking, and coverage limited to `researchos`. | `ARCHITECTURE_FORENSIC_REPORT.md` F7 and CI section. | HIGH — a green aggregate badge can coexist with unexecuted or non-failing verification surfaces. | Remove failure masking, include every intended test root, and require dedicated C++/numeric regression evidence before treating CI as a scientific verification result. | OPEN |

## Gate rule

Until findings **#1–#6** are closed with executable evidence, do not promote a new Bayesian engine, new hypothesis, or new scientific edge claim. Regression correctness comes first.

## Immediate next action

1. Remove the two pytest `--ignore` entries from the canonical test configuration.
2. Run the resulting regression suite in a C++-compiled, data-complete environment.
3. Record the first real PASS/FAIL outcome here.
4. If #4 fails, fix numeric parity before changing methodology.
