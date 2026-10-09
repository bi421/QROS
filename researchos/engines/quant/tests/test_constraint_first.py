from __future__ import annotations

import numpy as np
import pytest

from researchos.engines.quant.python.cpp_quant_engine.constraint_first import evaluate_candidates


def _native_available() -> bool:
    try:
        from cpp_quant_engine import qros_constraint_engine  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.cpp
@pytest.mark.skipif(not _native_available(), reason="compiled QROS C++ extension is not installed")
def test_known_forward_return_probabilities() -> None:
    closes = np.array([100.0, 101.0, 100.0, 102.0, 99.0, 103.0], dtype=np.float64)
    targets = np.array([100.0, 100.0], dtype=np.float64)
    horizons = np.array([1, 1], dtype=np.int32)
    directions = np.array([1, -1], dtype=np.int32)

    result = evaluate_candidates(closes, targets, horizons, directions)

    assert result["candle_count"] == 6
    assert result["unique_horizons"] == 1
    assert result["sample_size"] == [5, 5]
    assert result["probability"][0] == pytest.approx(3 / 5)
    assert result["probability"][1] == pytest.approx(1 / 5)


@pytest.mark.cpp
@pytest.mark.skipif(not _native_available(), reason="compiled QROS C++ extension is not installed")
def test_candidate_validation_fails_closed() -> None:
    closes = np.array([100.0, 101.0, 102.0], dtype=np.float64)
    with pytest.raises(ValueError, match="direction"):
        evaluate_candidates(
            closes,
            np.array([10.0]),
            np.array([1], dtype=np.int32),
            np.array([0], dtype=np.int32),
        )


@pytest.mark.cpp
@pytest.mark.skipif(not _native_available(), reason="compiled QROS C++ extension is not installed")
def test_unique_horizon_limit_is_enforced() -> None:
    closes = np.arange(1.0, 12.0, dtype=np.float64)
    with pytest.raises(ValueError, match="max_unique_horizons"):
        evaluate_candidates(
            closes,
            np.array([1.0, 2.0]),
            np.array([1, 2], dtype=np.int32),
            np.array([1, -1], dtype=np.int32),
            max_unique_horizons=1,
        )


@pytest.mark.cpp
@pytest.mark.skipif(not _native_available(), reason="compiled QROS C++ extension is not installed")
def test_candidate_pruning_uses_explicit_probability_and_sample_thresholds() -> None:
    closes = np.array([100.0, 101.0, 100.0, 102.0, 99.0, 103.0], dtype=np.float64)
    result = evaluate_candidates(
        closes,
        np.array([100.0, 100.0]),
        np.array([1, 1], dtype=np.int32),
        np.array([1, -1], dtype=np.int32),
        minimum_probability=0.3,
        minimum_samples=5,
    )

    assert result["survivor_indices"] == [0]
    assert result["rejected_indices"] == [1]


@pytest.mark.cpp
@pytest.mark.skipif(not _native_available(), reason="compiled QROS C++ extension is not installed")
def test_mixed_horizon_buckets_preserve_candidate_order_and_sample_counts() -> None:
    closes = np.array([100.0, 101.0, 99.0, 102.0, 98.0, 104.0, 100.0], dtype=np.float64)
    targets = np.array([100.0, 100.0, 200.0, 200.0], dtype=np.float64)
    horizons = np.array([2, 1, 2, 1], dtype=np.int32)
    directions = np.array([1, -1, -1, 1], dtype=np.int32)

    result = evaluate_candidates(closes, targets, horizons, directions)

    assert result["unique_horizons"] == 2
    assert result["sample_size"] == [5, 6, 5, 6]
    assert result["wins"] == [1, 3, 0, 2]
    assert result["probability"] == pytest.approx([1 / 5, 3 / 6, 0 / 5, 2 / 6])
