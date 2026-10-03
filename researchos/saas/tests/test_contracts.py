from uuid import uuid4

import pytest

from researchos.saas.contracts import DEFAULT_USAGE_POLICIES, Plan, TenantContext, UsagePolicy


def test_usage_policy_boundaries_are_explicit() -> None:
    policy = UsagePolicy(monthly_research_runs=2, max_dataset_bytes=100, max_concurrent_runs=1)
    assert policy.allows_monthly_runs(0)
    assert policy.allows_monthly_runs(1)
    assert not policy.allows_monthly_runs(2)
    assert policy.allows_dataset(100)
    assert not policy.allows_dataset(101)
    assert policy.allows_concurrency(0)
    assert not policy.allows_concurrency(1)


def test_enterprise_zero_means_unlimited() -> None:
    policy = DEFAULT_USAGE_POLICIES[Plan.ENTERPRISE]
    assert policy.allows_monthly_runs(1_000_000)
    assert policy.allows_dataset(10_000_000_000)
    assert policy.allows_concurrency(1_000)


def test_tenant_context_is_immutable() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.PRO)
    with pytest.raises(Exception):
        context.plan = Plan.ENTERPRISE  # type: ignore[misc]


def test_free_plan_allows_exactly_100_monthly_runs() -> None:
    policy = DEFAULT_USAGE_POLICIES[Plan.FREE]
    assert policy.monthly_research_runs == 100
    assert policy.allows_monthly_runs(99)
    assert not policy.allows_monthly_runs(100)
