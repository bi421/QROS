from __future__ import annotations

import math

import pytest


def test_parallel_research_wave_matches_reference_math() -> None:
    backend = pytest.importorskip("cpp_quant_backend")
    result = backend.parallel_research_wave([1.0, 2.0, 3.0, 4.0])

    assert result["sample_size"] == 4
    assert result["mean"] == pytest.approx(2.5)
    assert result["variance"] == pytest.approx(5.0 / 3.0)
    assert result["standard_deviation"] == pytest.approx(math.sqrt(5.0 / 3.0))
    assert result["linear_slope"] == pytest.approx(1.0)
    assert result["positive_rate"] == pytest.approx(1.0)


def test_parallel_research_wave_rejects_non_finite_values() -> None:
    backend = pytest.importorskip("cpp_quant_backend")

    with pytest.raises(ValueError, match="non-finite"):
        backend.parallel_research_wave([1.0, float("nan")])
