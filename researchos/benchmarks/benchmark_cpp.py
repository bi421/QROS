"""
Python vs C++ compute backend benchmark (Phase 4.3).

Measures wall-clock execution time for every ``QuantComputationInterface``
operation on both the Python reference backend and the certified C++ adapter,
over several dataset sizes.  Outputs a comparison table and the speedup per
operation.

Run with:

    python -m researchos.benchmarks.benchmark_cpp

The benchmark never asserts on speed — it is an observational performance
report.  When the compiled C++ engine is unavailable the C++ column shows the
Python fallback and speedup is 1.00x.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from researchos.quant_engine.backend import PythonQuantBackend
from researchos.quant_engine.cpp_backend import (
    CppQuantAdapter,
    has_cpp_engine,
)
from researchos.quant_engine.models import CalculationVersion, SimulationRequest

_V1 = CalculationVersion.CALCULATION_V1

#: Dataset sizes used by the benchmark (number of price observations).
DATASET_SIZES: tuple[int, ...] = (1_000, 10_000, 100_000)

#: Wall-clock budget per operation per size (seconds).
_BUDGET_SECONDS = 2.0


def make_prices(n: int, base: float = 100.0) -> list[float]:
    """Deterministic price series (no randomness)."""
    return [base + 30.0 * ((i % 17) / 17.0) + 0.5 * (i % 7) for i in range(n)]


def _equity(prices: list[float]) -> list[float]:
    """Build a deterministic equity curve from a price series."""
    equity = [100000.0]
    for r in make_returns(prices):
        equity.append(equity[-1] * (1.0 + r))
    return equity


def make_returns(prices: list[float]) -> list[float]:
    """Percentage returns from a price series (length n - 1)."""
    return [(prices[i] / prices[i - 1]) - 1.0 for i in range(1, len(prices))]


def make_request() -> SimulationRequest:
    return SimulationRequest(
        dataset_reference="BENCHMARK",
        dataset_version="1.0.0",
        calculation_version=_V1,
        start_time="2026-01-01T00:00:00",
        end_time="2026-12-31T00:00:00",
        parameters={"initial_capital": 100000.0, "risk_free_rate": 0.0},
        seed=42,
    )


def _time_once(fn: Callable[[], Any]) -> float:
    start = time.perf_counter()
    fn()
    return time.perf_counter() - start


def timed(fn: Callable[[], Any], budget: float = _BUDGET_SECONDS) -> float:
    """Time ``fn`` once, warming up first; returns elapsed seconds."""
    try:
        fn()
    except Exception:
        pass
    return _time_once(fn)


def build_cases(py: PythonQuantBackend, cpp: CppQuantAdapter) -> list[tuple[str, Callable[[list[float]], Any], Callable[[list[float]], Any]]]:
    """Return (name, python_call, cpp_call) pairs for every operation.

    Each callable is invoked with a per-size prepared fixture.
    """
    request = make_request()
    return [
        (
            "calculate_returns",
            lambda p: py.calculate_returns(p, "percentage"),
            lambda p: cpp.calculate_returns(p, "percentage"),
        ),
        (
            "calculate_volatility",
            lambda p: py.calculate_volatility(py.calculate_returns(p), "standard_deviation"),
            lambda p: cpp.calculate_volatility(cpp.calculate_returns(p), "standard_deviation"),
        ),
        (
            "calculate_statistics",
            lambda p: py.calculate_statistics(py.calculate_returns(p)),
            lambda p: cpp.calculate_statistics(cpp.calculate_returns(p)),
        ),
        (
            "calculate_metrics",
            lambda p: py.calculate_metrics(py.calculate_returns(p), _equity(p), 0.0),
            lambda p: cpp.calculate_metrics(cpp.calculate_returns(p), _equity(p), 0.0),
        ),
        (
            "calculate_performance_analytics",
            lambda p: py.calculate_performance_analytics(py.calculate_returns(p)),
            lambda p: cpp.calculate_performance_analytics(cpp.calculate_returns(p)),
        ),
        (
            "run_simulation",
            lambda p: py.run_simulation(request, p),
            lambda p: cpp.run_simulation(request, p),
        ),
    ]


def run_benchmark() -> dict[str, Any]:
    """Run the full benchmark and return a serializable results dict."""
    py = PythonQuantBackend()
    cpp = CppQuantAdapter()
    engine_available = has_cpp_engine()

    results: dict[str, Any] = {
        "python_backend": "PythonQuantBackend",
        "python_version": py.get_version(),
        "cpp_backend": "CppQuantAdapter" if engine_available else "unavailable (fallback)",
        "cpp_version": cpp.get_version() if engine_available else None,
        "sizes": list(DATASET_SIZES),
        "rows": [],
    }

    for name, py_fn, cpp_fn in build_cases(py, cpp):
        row: dict[str, Any] = {"operation": name, "measurements": []}
        for n in DATASET_SIZES:
            prices = make_prices(n)
            py_elapsed = timed(lambda p=prices: py_fn(p))
            cpp_elapsed = timed(lambda p=prices: cpp_fn(p))
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
    """Pretty-print the benchmark results dict."""
    print("=" * 92)
    print("ResearchOS — Python vs C++ Compute Backend Benchmark (Phase 4.3)")
    print("=" * 92)
    print(f"Python backend: {results['python_backend']} {results['python_version']}")
    print(f"C++ backend:    {results['cpp_backend']} {results.get('cpp_version') or ''}")
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
    "make_prices",
    "make_request",
    "run_benchmark",
    "print_results",
    "main",
]
