"""
Phase 4.5 — Regression & Rolling statistics: Python vs C++ backend benchmark.

Measures wall-clock execution time for the Regression and RollingWindow
operations that Phase 4.5 routes through the compiled C++ engine, comparing
them against the pure-Python reference implementations (validation-only).

Run with:

    python -m researchos.benchmarks.benchmark_cpp_performance_integration

The benchmark never asserts on speed — it is an observational performance
report.  When the compiled C++ engine is unavailable the C++ column shows the
Python fallback and speedup is 1.00x.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Any

from researchos.quant_engine.cpp_backend import CppQuantAdapter, has_cpp_engine
from researchos.quant_engine.statistics import (
    regression_correlation,
    regression_intercept,
    regression_r_squared,
    regression_slope,
    regression_standard_error,
    rolling_mean,
    rolling_variance_incremental,
    rolling_volatility_incremental,
)

#: Dataset sizes (number of observations).
DATASET_SIZES: tuple[int, ...] = (1_000, 10_000, 100_000)

_BUDGET_SECONDS = 2.0


def make_series(n: int, base: float = 100.0) -> list[float]:
    """Deterministic series (no randomness)."""
    return [base + 30.0 * math.sin(i / 5.0) + 0.5 * (i % 7) for i in range(n)]


def _time_once(fn: Callable[[], Any]) -> float:
    start = time.perf_counter()
    fn()
    return time.perf_counter() - start


def timed(fn: Callable[[], Any], budget: float = _BUDGET_SECONDS) -> float:
    try:
        fn()
    except Exception:
        pass
    return _time_once(fn)


def build_cases(
    cpp: CppQuantAdapter,
) -> list[tuple[str, Callable[[list[float]], Any], Callable[[list[float]], Any]]]:
    """Return (name, python_call, cpp_call) pairs for the new operations."""
    return [
        (
            "regression_slope",
            lambda s: regression_slope(s),
            lambda s: cpp.regression_slope(s),
        ),
        (
            "regression_intercept",
            lambda s: regression_intercept(s),
            lambda s: cpp.regression_intercept(s),
        ),
        (
            "regression_correlation",
            lambda s: regression_correlation(s, [v * 2 + 1 for v in s]),
            lambda s: cpp.regression_correlation(s, [v * 2 + 1 for v in s]),
        ),
        (
            "regression_r_squared",
            lambda s: regression_r_squared(s, [v * 2 + 1 for v in s]),
            lambda s: cpp.regression_r_squared(s, [v * 2 + 1 for v in s]),
        ),
        (
            "regression_standard_error",
            lambda s: regression_standard_error(s, [v * 2 + 1 for v in s]),
            lambda s: cpp.regression_standard_error(s, [v * 2 + 1 for v in s]),
        ),
        (
            "rolling_mean",
            lambda s: rolling_mean(s, 21),
            lambda s: cpp.rolling_mean(s, 21),
        ),
        (
            "rolling_volatility",
            lambda s: rolling_volatility_incremental(s, 21, ddof=1),
            lambda s: cpp.rolling_volatility_series(s, 21, ddof=1),
        ),
        (
            "rolling_variance",
            lambda s: rolling_variance_incremental(s, 21, ddof=1),
            lambda s: cpp.rolling_variance_series(s, 21, ddof=1),
        ),
    ]


def run_benchmark() -> dict[str, Any]:
    """Run the full benchmark and return a serializable results dict."""
    cpp = CppQuantAdapter()
    engine_available = has_cpp_engine()

    results: dict[str, Any] = {
        "cpp_backend": "CppQuantAdapter" if engine_available else "unavailable (fallback)",
        "cpp_version": cpp.get_version() if engine_available else None,
        "sizes": list(DATASET_SIZES),
        "rows": [],
    }

    for name, py_fn, cpp_fn in build_cases(cpp):
        row: dict[str, Any] = {"operation": name, "measurements": []}
        for n in DATASET_SIZES:
            series = make_series(n)
            py_elapsed = timed(lambda s=series: py_fn(s))
            cpp_elapsed = timed(lambda s=series: cpp_fn(s))
            speedup = py_elapsed / cpp_elapsed if cpp_elapsed > 0 else float("inf")
            row["measurements"].append(
                {
                    "size": n,
                    "python_s": round(py_elapsed, 6),
                    "cpp_s": round(cpp_elapsed, 6),
                    "speedup": round(speedup, 2),
                }
            )
        results["rows"].append(row)
    return results


def print_results(results: dict[str, Any]) -> None:
    print("=" * 92)
    print("ResearchOS — Regression & Rolling: Python vs C++ Benchmark (Phase 4.5)")
    print("=" * 92)
    print(f"C++ backend: {results['cpp_backend']} {results.get('cpp_version') or ''}")
    print()
    for row in results["rows"]:
        print(f"[{row['operation']}]")
        print(f"  {'size':>10} {'python (s)':>12} {'cpp (s)':>12} {'speedup':>10}")
        for m in row["measurements"]:
            print(f"  {m['size']:>10} {m['python_s']:>12.6f} {m['cpp_s']:>12.6f} {m['speedup']:>9.2f}x")
        print()


def main() -> None:
    print_results(run_benchmark())


if __name__ == "__main__":
    main()


__all__ = [
    "DATASET_SIZES",
    "make_series",
    "run_benchmark",
    "print_results",
    "main",
]
