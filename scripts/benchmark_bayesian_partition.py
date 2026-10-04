"""Small deterministic benchmark for Bayesian partition update scaling.

Usage:
    python scripts/benchmark_bayesian_partition.py

This is intentionally a benchmark script, not a correctness gate. The
algorithm is expected to remain O(N) in the number of hypotheses.
"""
from __future__ import annotations

import time

from researchos.quant_math.bayesian_update import bayesian_update
from researchos.quant_math.partition import ProbabilityPartition


def run(size: int) -> float:
    prior = tuple(1.0 / size for _ in range(size))
    likelihoods = tuple((i + 1.0) / size for i in range(size))
    partition = ProbabilityPartition.from_sequences(
        f"benchmark-{size}",
        [f"H{i}" for i in range(size)],
        prior,
    )
    started = time.perf_counter()
    result = bayesian_update(
        partition,
        event_id=f"benchmark-event-{size}",
        likelihoods=likelihoods,
        evidence_hash=f"benchmark-evidence-{size}",
    )
    result.verify()
    return time.perf_counter() - started


if __name__ == "__main__":
    for size in (10, 100, 1_000, 10_000):
        elapsed = run(size)
        print(f"hypotheses={size:>5} elapsed_seconds={elapsed:.6f}")
