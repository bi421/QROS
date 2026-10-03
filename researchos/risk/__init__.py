"""ResearchOS decision-risk boundary.

The package exposes the original risk.v1 sizing layer plus the governed
account and pre-trade control layer. Nothing here creates or submits orders.
"""

from researchos.risk.adapters import risk_input_from_probability
from researchos.risk.contracts import (
    RiskCalculation,
    RiskInput,
    RiskPolicy,
    TradeStatistics,
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
    "RiskCalculation",
    "RiskInput",
    "RiskPolicy",
    "TradeStatistics",
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
