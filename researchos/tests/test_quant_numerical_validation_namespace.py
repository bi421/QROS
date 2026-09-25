"""Namespace compatibility tests for numerical validation."""

from __future__ import annotations

import math

import pytest

from researchos.engines.quant import numerical_validation as legacy
from researchos.quant_engine import numerical_validation as canonical


def test_legacy_public_api_is_canonical() -> None:
    assert legacy.__all__ == canonical.__all__
    for name in canonical.__all__:
        assert getattr(legacy, name) is getattr(canonical, name)


def test_numeric_comparison_contract() -> None:
    comparator = legacy.NumericalComparator()
    passed = comparator.compare_matrix(
        [[1.0, 2.0], [3.0, 4.0]],
        [[1.0, 2.0 + 1e-14], [3.0, 4.0]],
    )
    assert passed.passed is True
    assert passed.shape_match is True
    assert passed.has_nan is False
    assert passed.has_inf is False
    assert passed.atol == canonical.NumericalComparator.DEFAULT_ATOL
    assert passed.rtol == canonical.NumericalComparator.DEFAULT_RTOL


@pytest.mark.parametrize(
    ("expected", "actual", "attribute"),
    [
        ([1.0, math.nan], [1.0, 2.0], "has_nan"),
        ([1.0, math.inf], [1.0, 2.0], "has_inf"),
        ([1.0, 2.0], [1.0], "shape_match"),
    ],
)
def test_invalid_numeric_boundaries_match(
    expected: object,
    actual: object,
    attribute: str,
) -> None:
    result = legacy.NumericalComparator().compare(expected, actual)  # type: ignore[arg-type]
    assert result.passed is False
    assert getattr(result, attribute) is False if attribute == "shape_match" else getattr(result, attribute) is True


@pytest.mark.parametrize(
    ("atol", "rtol"),
    [(-1.0, 1e-10), (1e-12, -1.0)],
)
def test_invalid_tolerances_preserve_exception(
    atol: float,
    rtol: float,
) -> None:
    with pytest.raises(legacy.NumericalComparisonError) as exc:
        legacy.NumericalComparator().compare_scalar(1.0, 1.0, atol=atol, rtol=rtol)
    assert str(exc.value) in {
        "atol must be a non-negative number",
        "rtol must be a non-negative number",
    }


def test_result_serialization_and_determinism() -> None:
    comparator = legacy.NumericalComparator()
    first = comparator.compare_vector([1.0, 2.0], [1.0, 2.0])
    second = comparator.compare_vector([1.0, 2.0], [1.0, 2.0])

    assert first == canonical.NumericalValidationResult.from_dict(first.to_dict())
    assert first.comparison_hash == second.comparison_hash
    assert len(first.comparison_hash) == 64


def test_structural_comparison_and_backend_hash() -> None:
    comparator = legacy.NumericalComparator()
    expected = {"value": 1.0, "items": [2, 3]}
    actual = {"items": [2, 3], "value": 1.0}

    result = comparator.compare_structural(expected, actual)
    assert result.passed is True
    assert result.mode == "structural"
    assert result.comparison_hash == comparator.compare_structural(expected, actual).comparison_hash

    from researchos.engines.quant.backend_hash import canonicalize as legacy_canonicalize
    from researchos.quant_engine.backend_hash import canonicalize as canonical_canonicalize

    assert legacy_canonicalize(expected) == canonical_canonicalize(expected)
    assert legacy_canonicalize(expected) == {"items": [2, 3], "value": "1.0"}
