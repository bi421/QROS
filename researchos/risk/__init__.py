"""ResearchOS decision-risk boundary.

The package exposes deterministic sizing, governed account controls, and
hash-linked human-review artifacts. Nothing here creates or submits orders.
"""

from researchos.risk.adapters import risk_input_from_probability
from researchos.risk.contracts import RiskCalculation, RiskInput, RiskPolicy, TradeStatistics
from researchos.risk.decision_artifact import (
    RISK_DECISION_ARTIFACT_VERSION,
    RiskDecisionArtifact,
    build_risk_decision_artifact,
)
from researchos.risk.decision_artifact_store import (
    InMemoryRiskDecisionArtifactStore,
    RiskDecisionArtifactStore,
)
from researchos.risk.engine import calculate_risk
from researchos.risk.governance import (
    RISK_GOVERNANCE_SCHEMA_VERSION,
    RiskAccountState,
    RiskDecision,
    RiskLimits,
    RiskViolation,
    RiskViolationCode,
    StrategyRiskState,
    StrategyStateTransitionError,
    evaluate_pretrade_risk,
    validate_strategy_transition,
)

__all__ = [
    "RISK_GOVERNANCE_SCHEMA_VERSION",
    "RISK_DECISION_ARTIFACT_VERSION",
    "RiskCalculation",
    "RiskInput",
    "RiskPolicy",
    "TradeStatistics",
    "RiskDecisionArtifact",
    "RiskDecisionArtifactStore",
    "InMemoryRiskDecisionArtifactStore",
    "build_risk_decision_artifact",
    "calculate_risk",
    "risk_input_from_probability",
    "RiskAccountState",
    "RiskDecision",
    "RiskLimits",
    "RiskViolation",
    "RiskViolationCode",
    "StrategyRiskState",
    "StrategyStateTransitionError",
    "evaluate_pretrade_risk",
    "validate_strategy_transition",
]
