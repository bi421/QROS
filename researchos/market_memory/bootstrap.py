"""
Bootstrap Engine — deterministic bootstrap uncertainty quantification.

Provides IID bootstrap when independence is defensible and a circular
moving-block bootstrap for ordered observations with local dependence.
The block size is part of statistical provenance.
"""
from __future__ import annotations

import math
import random
from typing import Any, Sequence

from researchos.market_memory.event_schema import BootstrapResult


def _validate_bootstrap_parameters(values: Sequence[float], num_resamples: int, confidence_level: float) -> None:
    if not values:
        raise ValueError("values cannot be empty")
    if num_resamples < 1:
        raise ValueError("num_resamples must be >= 1")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be strictly between 0 and 1")


def _percentile(sorted_values: Sequence[float], p: float) -> float:
    if not sorted_values:
        raise ValueError("sorted_values cannot be empty")
    k = (len(sorted_values) - 1) * p
    lower = math.floor(k)
    upper = math.ceil(k)
    if lower == upper:
        return float(sorted_values[lower])
    weight = k - lower
    return float(sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight)


def bootstrap_mean_ci(values: Sequence[float], num_resamples: int = 1000, seed: int = 42, confidence_level: float = 0.95) -> BootstrapResult:
    """Compute a deterministic percentile IID-bootstrap CI for the mean."""
    _validate_bootstrap_parameters(values, num_resamples, confidence_level)
    rng = random.Random(seed)
    n = len(values)
    point_estimate = sum(values) / n
    resample_means = [sum(rng.choice(values) for _ in range(n)) / n for _ in range(num_resamples)]
    resample_means.sort()
    bootstrap_mean_val = sum(resample_means) / len(resample_means)
    bootstrap_std = math.sqrt(sum((x - bootstrap_mean_val) ** 2 for x in resample_means) / len(resample_means))
    alpha = 1.0 - confidence_level
    return BootstrapResult(
        point_estimate=point_estimate,
        bootstrap_mean=bootstrap_mean_val,
        bootstrap_std=bootstrap_std,
        confidence_interval=(_percentile(resample_means, alpha / 2.0), _percentile(resample_means, 1.0 - alpha / 2.0)),
        confidence_level=confidence_level,
        num_resamples=num_resamples,
        seed=seed,
        method="percentile_bootstrap",
    )


def block_bootstrap_mean_ci(values: Sequence[float], block_size: int, num_resamples: int = 1000, seed: int = 42, confidence_level: float = 0.95) -> BootstrapResult:
    """Deterministic circular moving-block bootstrap for an ordered mean.

    Blocks preserve within-block order and are sampled with replacement.
    This assumes dependence is predominantly local within the chosen block.
    block_size=1 is exactly the IID bootstrap special case.
    """
    _validate_bootstrap_parameters(values, num_resamples, confidence_level)
    if not isinstance(block_size, int):
        raise TypeError("block_size must be an int")
    if block_size < 1:
        raise ValueError("block_size must be >= 1")
    if block_size > len(values):
        raise ValueError("block_size cannot exceed sample size")
    if block_size == 1:
        return bootstrap_mean_ci(values, num_resamples, seed, confidence_level)

    rng = random.Random(seed)
    n = len(values)
    point_estimate = sum(values) / n
    starts = list(range(n))
    resample_means: list[float] = []
    for _ in range(num_resamples):
        sample: list[float] = []
        while len(sample) < n:
            start = rng.choice(starts)
            sample.extend(values[(start + offset) % n] for offset in range(block_size))
        sample = sample[:n]
        resample_means.append(sum(sample) / n)
    resample_means.sort()
    bootstrap_mean_val = sum(resample_means) / len(resample_means)
    bootstrap_std = math.sqrt(sum((x - bootstrap_mean_val) ** 2 for x in resample_means) / len(resample_means))
    alpha = 1.0 - confidence_level
    return BootstrapResult(
        point_estimate=point_estimate,
        bootstrap_mean=bootstrap_mean_val,
        bootstrap_std=bootstrap_std,
        confidence_interval=(_percentile(resample_means, alpha / 2.0), _percentile(resample_means, 1.0 - alpha / 2.0)),
        confidence_level=confidence_level,
        num_resamples=num_resamples,
        seed=seed,
        method="circular_moving_block_bootstrap",
    )


def bootstrap_stability_check(values: Sequence[float], num_resamples: int = 1000, seed: int = 42, threshold: float = 0.1) -> dict[str, Any]:
    """Check if IID bootstrap CI is stable."""
    result = bootstrap_mean_ci(values, num_resamples, seed)
    ci_width = result.confidence_interval[1] - result.confidence_interval[0]
    relative_width = ci_width / abs(result.point_estimate) if result.point_estimate != 0 else float("inf")
    return {
        "point_estimate": result.point_estimate,
        "ci_width": ci_width,
        "relative_width": relative_width,
        "is_stable": relative_width < threshold,
        "threshold": threshold,
    }
