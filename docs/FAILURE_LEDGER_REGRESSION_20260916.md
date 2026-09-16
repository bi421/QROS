# Failure Ledger — Regression Verification Audit

**Date:** 2026-09-16  
**Scope:** ResearchOS scientific/regression verification only  
**Status:** OPEN — no Bayesian engine or new hypothesis work permitted until these verification gaps are resolved.

This ledger records concrete regression blind spots found in repository evidence. A test-count/CI badge is not treated as proof of numeric correctness.

| # | Finding | Evidence | Risk | Required verification | Status |
|---|---|---|---|---|---|
| 1 | **Percentage-return scaling contract is regression-sensitive.** A historical C++ regression test multiplied `winrate` and `total_return` by 100 even though the API values were already percentages; this was fixed in commit `28d7a4e`. | Commit `28d7a4e` explicitly fixes the double-`*100` bug in `test_cpp_backtest_regression.py`. The repository also has a fractional percentage-return contract test: `0.02` means 2%, not 2.0. | HIGH — a factor-100 error can make a numerically wrong result look plausible or make a valid result fail a range test. | C++ regression now checks the exact fractional return contract against fixed expected values and the Python backend. | VERIFICATION PENDING CI |
| 2 | **C++ backend availability can be hidden by fallback architecture.** ResearchOS has a Python fallback boundary, so generic Python tests can pass without exercising compiled C++ numerics. | Current C++ regression fixture fails when `CppQuantAdapter.is_cpp` is false. CI now builds the C++ backend before the canonical Python suite and the regression fixture refuses fallback execution. | HIGH — a green Python suite is not equivalent to C++ numeric verification. | Obtain CI evidence that the canonical suite executes with the compiled backend active. | VERIFICATION PENDING CI |
| 3 | **The canonical pytest configuration historically excluded the C++ backtest regression test.** | `pyproject.toml` previously contained `--ignore=researchos/tests/test_cpp_backtest_regression.py` and `--ignore=cpp_quant_engine`. Both entries are now removed; `addopts = "-v --tb=short"`. | HIGH — the test can exist and remain green while never being collected by the normal suite. | Confirm the unignored test is collected and produces a real PASS/FAIL result. | FIXED — AWAITING CI EVIDENCE |
| 4 | **Backtest numeric correctness was not fully asserted by the previous regression test.** The previous test independently calculated winrate/total return in Python, but C++ `statistics`/`metrics` were only asserted non-empty. | The regression test now computes independent Python reference statistics/metrics and compares field-by-field against C++ values, plus compares the complete C++ return series. | CRITICAL — a C++ metric could be numerically wrong while the old test still passed. | CI must pass the exact parity assertions for count, mean, sum, std, total return, mean/std return, downside deviation, max drawdown, win rate, profit factor, annualised return/volatility, and return series. | IMPLEMENTED — AWAITING CI EVIDENCE |
| 5 | **The previous regression test was data-dependent on `data/raw/histdata/xauusd`.** | The old test failed when the user-local XAUUSD directory/files were absent. It is now replaced by a deterministic in-repository-generated daily fixture, so the regression no longer depends on private/local market data. | HIGH — environmental data availability could mask or create failures unrelated to numeric correctness. | Confirm the deterministic regression executes in CI without external/user-local data. | FIXED — AWAITING CI EVIDENCE |
| 6 | **CI coverage can have verification blind spots beyond the headline Python test count.** The architecture forensic audit documented package-local test roots omitted from CI, C++ `ctest || echo` failure masking, and coverage limited to `researchos`. | Current CI already uses a failing `ctest` command and now builds the C++ backend for the canonical Python suite. Remaining scope/coverage claims require separate audit evidence. | HIGH — a green aggregate badge can coexist with unexecuted or non-failing verification surfaces. | Verify the new CI run and then audit remaining omitted roots/coverage boundaries before closing this finding. | PARTIALLY ADDRESSED — VERIFICATION PENDING |

## Gate rule

Until findings **#1–#6** are closed with executable evidence, do not promote a new Bayesian engine, new hypothesis, or new scientific edge claim. Regression correctness comes first.

## Latest CI failure classification

CI #822 failed in **Python Tests + Coverage (3.11)** during the `Test + coverage` step; the separate **Quant Engine (C++ / nanobind)** job passed its configure, build, CTest, benchmark, and Python quant-integration steps. The exact failing test output was not available through the GitHub log endpoint. Therefore #822 is recorded as an execution failure, not as proof of a numeric regression.

The next revision specifically addresses the two concrete causes exposed by the unignored test surface: the regression test no longer requires user-local XAUUSD files, and the canonical Python test job now builds and exposes the compiled C++ backend before pytest.

## Immediate next action

1. Run CI on the new harness commit.
2. If it fails, classify the first failing test from the actual pytest output before changing implementation code.
3. If it passes, record the exact test count and close #1–#5 only where the executable evidence supports closure.
4. Audit the remaining CI test-root/coverage blind spots for #6.
5. Only after regression correctness is verified may scientific methodology work resume.
