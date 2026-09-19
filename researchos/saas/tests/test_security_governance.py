from __future__ import annotations

import pytest

from researchos.saas.security_governance import (
    ChangeRisk,
    TrustDomain,
    execution_side_effect_allowed,
    require_explicit_tenant_context,
    requirements_for,
)


def test_risk_requirements_escalate_at_trust_boundaries() -> None:
    r0 = requirements_for(ChangeRisk.R0)
    r1 = requirements_for(ChangeRisk.R1)
    r2 = requirements_for(ChangeRisk.R2)
    r3 = requirements_for(ChangeRisk.R3)

    assert not r0.requires_unit_tests
    assert r1.requires_unit_tests
    assert r1.requires_failure_tests
    assert not r1.requires_integration_tests
    assert r2.requires_integration_tests
    assert not r2.requires_tenant_isolation
    assert r3.requires_tenant_isolation
    assert r3.requires_security_review
    assert r3.requires_recovery_analysis
    assert r3.requires_target_environment_verification


def test_execution_domain_rejects_direct_entry_from_research_and_saas() -> None:
    assert not execution_side_effect_allowed(
        TrustDomain.RESEARCH, TrustDomain.EXECUTION
    )
    assert not execution_side_effect_allowed(
        TrustDomain.SAAS_CONTROL, TrustDomain.EXECUTION
    )
    assert execution_side_effect_allowed(
        TrustDomain.EXECUTION, TrustDomain.EXECUTION
    )


def test_tenant_authority_fails_closed_when_missing() -> None:
    with pytest.raises(PermissionError, match="authorized tenant context"):
        require_explicit_tenant_context(None)


def test_tenant_authority_accepts_explicit_context() -> None:
    require_explicit_tenant_context(object())
