from __future__ import annotations

import math

import pytest

from researchos.engines.quant.probability import (
    generic_grid_mle,
    mle_log_normal,
    mle_normal,
    mle_student_t,
)
from researchos.quant_engine.probability.mle import (
    generic_grid_mle as canonical_generic_grid_mle,
    mle_log_normal as canonical_mle_log_normal,
    mle_normal as canonical_mle_normal,
    mle_student_t as canonical_mle_student_t,
)


def test_mle_namespace_behavior_matches_canonical() -> None:
    samples = [1.0, 2.0, 3.0, 4.0]

    legacy_normal = mle_normal(samples)
    canonical_normal = canonical_mle_normal(samples)

    assert legacy_normal.distribution == canonical_normal.distribution
    assert legacy_normal.parameters == canonical_normal.parameters
    assert math.isclose(
        legacy_normal.log_likelihood,
        canonical_normal.log_likelihood,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )
    assert legacy_normal.sample_size == canonical_normal.sample_size

    legacy_log_normal = mle_log_normal([1.0, 2.0, 4.0])
    canonical_log_normal = canonical_mle_log_normal([1.0, 2.0, 4.0])

    assert legacy_log_normal.distribution == canonical_log_normal.distribution
    assert legacy_log_normal.parameters == canonical_log_normal.parameters
    assert math.isclose(
        legacy_log_normal.log_likelihood,
        canonical_log_normal.log_likelihood,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )

    df_grid = (3.0, 5.0, 8.0, 12.0)
    legacy_student_t = mle_student_t(samples, df_grid=df_grid)
    canonical_student_t = canonical_mle_student_t(samples, df_grid=df_grid)

    assert legacy_student_t.distribution == canonical_student_t.distribution
    assert legacy_student_t.parameters == canonical_student_t.parameters
    assert math.isclose(
        legacy_student_t.log_likelihood,
        canonical_student_t.log_likelihood,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )

    def likelihood(params: dict[str, float]) -> float:
        return -((params["mu"] - 2.0) ** 2 + (params["sigma"] - 1.0) ** 2)

    legacy_grid = generic_grid_mle(
        samples,
        likelihood,
        {"mu": (1.0, 2.0, 3.0), "sigma": (0.5, 1.0, 1.5)},
    )
    canonical_grid = canonical_generic_grid_mle(
        samples,
        likelihood,
        {"mu": (1.0, 2.0, 3.0), "sigma": (0.5, 1.0, 1.5)},
    )

    assert legacy_grid == canonical_grid == {"mu": 2.0, "sigma": 1.0}


def test_log_normal_rejects_non_positive_samples() -> None:
    with pytest.raises(ValueError, match="strictly positive"):
        mle_log_normal([1.0, 0.0, 2.0])


def test_mle_rejects_empty_samples() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        mle_normal([])

    with pytest.raises(ValueError, match="non-empty"):
        mle_log_normal([])

    with pytest.raises(ValueError, match="non-empty"):
        mle_student_t([])


def test_generic_grid_mle_rejects_empty_parameter_grid() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        generic_grid_mle([], lambda _: 0.0, {})


def test_student_t_is_deterministic() -> None:
    samples = [0.5, 1.0, 1.5, 2.0, 2.5]
    df_grid = (3.0, 5.0, 10.0)

    first = mle_student_t(samples, df_grid=df_grid)
    second = mle_student_t(samples, df_grid=df_grid)

    assert first.parameters == second.parameters
    assert first.sample_size == second.sample_size
    assert math.isclose(
        first.log_likelihood,
        second.log_likelihood,
        rel_tol=0.0,
        abs_tol=0.0,
    )


def test_canonical_functions_are_reachable_from_canonical_module() -> None:
    assert callable(canonical_mle_normal)
    assert callable(canonical_mle_log_normal)
    assert callable(canonical_mle_student_t)
    assert callable(canonical_generic_grid_mle)
