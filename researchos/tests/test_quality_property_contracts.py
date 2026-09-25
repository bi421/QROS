"""Property-based contract tests for high-value deterministic boundaries."""

from typing import cast
from uuid import UUID, uuid4

from hypothesis import given, settings, strategies as st

from researchos.quant_engine.numerical_validation import (
    NumericalComparator,
    NumericalComparisonError,
    NumericShape,
    NumericalValidationResult,
    ValidationStatus,
)
from researchos.saas.contracts import UsagePolicy
from researchos.saas.datasets import storage_path_for


FINITE_FLOATS = st.floats(
    min_value=-1_000_000.0,
    max_value=1_000_000.0,
    allow_nan=False,
    allow_infinity=False,
    width=64,
)


@settings(max_examples=50, derandomize=True)
@given(
    workspace=st.uuids(),
    digest=st.text(
        alphabet=st.characters(
            whitelist_categories=("Ll", "Lu", "Nd"),
        ),
        min_size=64,
        max_size=64,
    ),
    version=st.integers(min_value=1, max_value=100_000),
)
def test_storage_path_for_is_deterministic_and_int_string_equivalent(
    workspace: UUID,
    digest: str,
    version: int,
) -> None:
    integer_path = storage_path_for(workspace, digest, version)
    string_path = storage_path_for(workspace, digest, str(version))

    assert integer_path == string_path
    assert integer_path.endswith(f"/{version}/")


@settings(max_examples=50, derandomize=True)
@given(value=FINITE_FLOATS)
def test_numerical_validation_round_trip_preserves_finite_scalars(value: float) -> None:
    result = NumericalComparator().compare(value, value)

    assert result.status is ValidationStatus.PASSED
    assert result.passed
    assert result.has_nan is False
    assert result.has_inf is False

    restored = NumericalValidationResult.from_dict(result.to_dict())
    assert restored == result


@settings(max_examples=50, derandomize=True)
@given(
    expected=FINITE_FLOATS,
    actual=FINITE_FLOATS,
)
def test_numerical_comparison_is_deterministic_for_bounded_finite_inputs(
    expected: float,
    actual: float,
) -> None:
    comparator = NumericalComparator()
    first = comparator.compare(expected, actual)
    second = comparator.compare(expected, actual)

    assert first.comparison_hash == second.comparison_hash
    assert first.to_dict() == second.to_dict()


@settings(max_examples=50, derandomize=True)
@given(
    monthly=st.integers(min_value=0, max_value=1000),
    dataset=st.integers(min_value=0, max_value=1000),
    concurrent=st.integers(min_value=0, max_value=100),
)
def test_usage_policy_rejects_negative_usage_and_honors_limits(
    monthly: int,
    dataset: int,
    concurrent: int,
) -> None:
    policy = UsagePolicy(
        monthly_research_runs=monthly,
        max_dataset_bytes=dataset,
        max_concurrent_runs=concurrent,
    )

    assert not policy.allows_monthly_runs(-1)
    assert not policy.allows_dataset(-1)
    assert not policy.allows_concurrency(-1)

    if monthly > 0:
        assert policy.allows_monthly_runs(monthly - 1)
        assert not policy.allows_monthly_runs(monthly)

    if dataset > 0:
        assert policy.allows_dataset(dataset)
        assert not policy.allows_dataset(dataset + 1)

    if concurrent > 0:
        assert policy.allows_concurrency(concurrent - 1)
        assert not policy.allows_concurrency(concurrent)


def test_runtime_boundary_rejects_malformed_external_version() -> None:
    malformed = cast(object, "not-an-integer")

    try:
        storage_path_for(uuid4(), "a" * 64, malformed)  # type: ignore[arg-type]
    except ValueError as exc:
        assert "version_no must be a valid integer" in str(exc)
    else:
        raise AssertionError("malformed external version must be rejected")


def test_runtime_boundary_rejects_non_numeric_comparison_input() -> None:
    malformed = cast(NumericShape, "not-numeric")

    try:
        NumericalComparator().compare(malformed, 1.0)
    except NumericalComparisonError as exc:
        assert str(exc) == "expected a scalar, vector, or matrix of numbers"
    else:
        raise AssertionError("malformed external numeric input must be rejected")
