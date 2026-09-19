"""Machine-readable security and architecture governance contracts.

These contracts are intentionally small and dependency-free so CI and tests can
assert the QROS trust-boundary rules without importing application frameworks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ChangeRisk(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"


class TrustDomain(StrEnum):
    RESEARCH = "research"
    SAAS_CONTROL = "saas_control"
    PERSISTENCE = "persistence"
    OPERATOR = "operator"
    EXECUTION = "execution"


@dataclass(frozen=True)
class GovernanceRequirement:
    risk: ChangeRisk
    requires_unit_tests: bool
    requires_failure_tests: bool
    requires_integration_tests: bool
    requires_tenant_isolation: bool
    requires_security_review: bool
    requires_recovery_analysis: bool
    requires_target_environment_verification: bool


def requirements_for(risk: ChangeRisk) -> GovernanceRequirement:
    if risk is ChangeRisk.R0:
        return GovernanceRequirement(risk, False, False, False, False, False, False, False)
    if risk is ChangeRisk.R1:
        return GovernanceRequirement(risk, True, True, False, False, False, False, False)
    if risk is ChangeRisk.R2:
        return GovernanceRequirement(risk, True, True, True, False, False, False, False)
    return GovernanceRequirement(risk, True, True, True, True, True, True, True)


def execution_side_effect_allowed(source: TrustDomain, target: TrustDomain) -> bool:
    """Return whether a direct side-effect boundary is permitted.

    Research and SaaS code must not directly enter the future execution domain.
    """
    if target is TrustDomain.EXECUTION:
        return source is TrustDomain.EXECUTION
    return True


def require_explicit_tenant_context(tenant_context: object | None) -> None:
    """Reject missing tenant authority rather than inferring it."""
    if tenant_context is None:
        raise PermissionError("authorized tenant context is required")


__all__ = [
    "ChangeRisk",
    "GovernanceRequirement",
    "TrustDomain",
    "execution_side_effect_allowed",
    "require_explicit_tenant_context",
    "requirements_for",
]
