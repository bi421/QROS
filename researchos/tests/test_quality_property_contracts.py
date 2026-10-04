"""Property-based contract tests for high-value deterministic boundaries."""

from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from hypothesis import given, settings, strategies as st

from researchos.quant_engine.numerical_validation import (
    NumericalComparator,
    NumericalComparisonError,
    NumericShape,
    NumericalValidationResult,
    ValidationStatus,
)
from researchos.quant_engine.backend_hash import canonicalize, compute_input_hash
from researchos.saas.contracts import UsagePolicy
from researchos.saas.datasets import storage_path_for
from researchos.saas.idempotency import (
    IdempotencyConflict,
    IdempotencyRecord,
    InMemoryIdempotencyStore,
)
from researchos.saas.pagination import paginate, validate_filter_tenant_id


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
    digest=st.from_regex(r"[0-9a-f]{64}", fullmatch=True),
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
    malformed = "not-an-integer"

    try:
        storage_path_for(uuid4(), "a" * 64, malformed)
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


JSON_SCALARS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-1_000, max_value=1_000),
    st.text(min_size=0, max_size=20),
    FINITE_FLOATS,
)
JSON_VALUES = st.recursive(
    JSON_SCALARS,
    lambda children: st.one_of(
        st.lists(children, min_size=0, max_size=5),
        st.dictionaries(
            st.text(min_size=1, max_size=12),
            children,
            min_size=0,
            max_size=5,
        ),
    ),
    max_leaves=20,
)


@settings(max_examples=50, derandomize=True)
@given(value=JSON_VALUES)
def test_canonicalize_is_idempotent(value: object) -> None:
    first = canonicalize(value)
    second = canonicalize(first)

    assert second == first


@settings(max_examples=50, derandomize=True)
@given(
    payload=st.dictionaries(
        st.text(min_size=1, max_size=12),
        JSON_VALUES,
        min_size=0,
        max_size=8,
    )
)
def test_compute_input_hash_is_invariant_to_mapping_insertion_order(
    payload: dict[str, object],
) -> None:
    reversed_payload = dict(reversed(list(payload.items())))

    assert compute_input_hash(payload) == compute_input_hash(reversed_payload)


@dataclass(frozen=True)
class _PageItem:
    value: int


@settings(max_examples=50, derandomize=True)
@given(
    values=st.lists(
        st.integers(min_value=-1_000, max_value=1_000),
        min_size=0,
        max_size=30,
        unique=True,
    ),
    page=st.integers(min_value=1, max_value=10),
    page_size=st.integers(min_value=1, max_value=5),
    sort_order=st.sampled_from(["asc", "desc"]),
)
def test_paginate_returns_exact_sorted_page_and_metadata(
    values: list[int],
    page: int,
    page_size: int,
    sort_order: str,
) -> None:
    items = [_PageItem(value=value) for value in values]
    expected = sorted(values, reverse=sort_order == "desc")
    start = (page - 1) * page_size
    expected_page = expected[start : start + page_size]
    expected_total_pages = (
        (len(expected) + page_size - 1) // page_size if expected else 0
    )

    result = paginate(
        items,
        page=page,
        page_size=page_size,
        sort_by="value",
        sort_order=sort_order,
    )

    assert result["data"] == [{"value": value} for value in expected_page]
    assert result["pagination"] == {
        "page": page,
        "page_size": page_size,
        "total": len(expected),
        "total_pages": expected_total_pages,
    }


@settings(max_examples=50, derandomize=True)
@given(workspace=st.uuids(), candidate=st.uuids())
def test_validate_filter_tenant_id_rejects_cross_tenant_filters(
    workspace: UUID,
    candidate: UUID,
) -> None:
    if candidate == workspace:
        validate_filter_tenant_id(candidate, workspace)
        return

    with pytest.raises(HTTPException) as exc_info:
        validate_filter_tenant_id(candidate, workspace)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "INVALID_FILTER"


@settings(max_examples=50, derandomize=True)
@given(
    workspaces=st.tuples(st.uuids(), st.uuids()).filter(lambda pair: pair[0] != pair[1]),
    key=st.text(min_size=1, max_size=64),
    fingerprint=st.text(min_size=1, max_size=64),
)
def test_idempotency_store_is_tenant_scoped_and_repeatable(
    workspaces: tuple[UUID, UUID],
    key: str,
    fingerprint: str,
) -> None:
    first_workspace, second_workspace = workspaces
    store = InMemoryIdempotencyStore()
    first = IdempotencyRecord(
        workspace_id=first_workspace,
        key=key,
        request_fingerprint=fingerprint,
        status_code=202,
        response_body={"workspace": str(first_workspace)},
    )
    second = IdempotencyRecord(
        workspace_id=second_workspace,
        key=key,
        request_fingerprint=fingerprint,
        status_code=202,
        response_body={"workspace": str(second_workspace)},
    )

    store.put(first)
    store.put(first)
    store.put(second)

    assert store.get(first_workspace, key) == first
    assert store.get(second_workspace, key) == second


@settings(max_examples=50, derandomize=True)
@given(
    key=st.text(min_size=1, max_size=64),
    fingerprint_a=st.text(min_size=1, max_size=64),
    fingerprint_b=st.text(min_size=1, max_size=64),
)
def test_idempotency_store_rejects_fingerprint_reuse_for_same_key(
    key: str,
    fingerprint_a: str,
    fingerprint_b: str,
) -> None:
    if fingerprint_a == fingerprint_b:
        return

    workspace = uuid4()
    store = InMemoryIdempotencyStore()
    store.put(
        IdempotencyRecord(
            workspace_id=workspace,
            key=key,
            request_fingerprint=fingerprint_a,
            status_code=202,
            response_body={"status": "first"},
        )
    )

    with pytest.raises(IdempotencyConflict):
        store.put(
            IdempotencyRecord(
                workspace_id=workspace,
                key=key,
                request_fingerprint=fingerprint_b,
                status_code=202,
                response_body={"status": "second"},
            )
        )
