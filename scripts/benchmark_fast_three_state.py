"""Read-only microbenchmark for the minimal three-state hot path."""

from __future__ import annotations

import math
import statistics
import time

from researchos.orchestration.fast_three_state import FastThreeState
from researchos.orchestration.incremental_regime import IncrementalRegimeEngine


def bars(count: int):
    for i in range(count):
        yield 2000.0 + i * 0.0003 + math.sin(i / 17.0) * 0.8


def batch(factory, count: int, repeats: int = 5):
    results = []
    for _ in range(repeats):
        engine = factory()
        start = time.perf_counter_ns()
        for close in bars(count):
            if isinstance(engine, FastThreeState):
                engine.update(close)
            else:
                engine.update(close + 0.5, close - 0.5, close)
        results.append((time.perf_counter_ns() - start) / count)
    return {
        "count_per_run": count,
        "repeats": repeats,
        "median_ns_per_candle": round(statistics.median(results), 1),
        "repeat_ns_per_candle": [round(value, 1) for value in results],
        "rows_per_second_from_median": round(1e9 / statistics.median(results), 1),
    }


def individual_latency(count: int = 10_000):
    engine = FastThreeState()
    for close in bars(100):
        engine.update(close)
    samples = []
    for close in bars(count):
        start = time.perf_counter_ns()
        engine.update(close)
        samples.append(time.perf_counter_ns() - start)
    samples.sort()
    return {
        "p50_ns": samples[int(0.50 * (len(samples) - 1))],
        "p95_ns": samples[int(0.95 * (len(samples) - 1))],
        "p99_ns": samples[int(0.99 * (len(samples) - 1))],
        "sample_count": len(samples),
        "note": "Individual measurements include timer/call overhead; batch throughput is the stronger speed estimate.",
    }


if __name__ == "__main__":
    print(
        "synthetic close-only workload; no network, disk, model, or report in hot path", flush=True
    )
    print(f"fast_three_state: {batch(FastThreeState, 100_000, 5)}", flush=True)
    print(f"existing_incremental_engine: {batch(IncrementalRegimeEngine, 2_000, 3)}", flush=True)
    print(f"fast_three_state individual latency: {individual_latency()}", flush=True)
