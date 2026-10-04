"""Pure decision-risk mathematics for the ResearchOS boundary."""

from __future__ import annotations

from researchos.risk.contracts import RISK_SCHEMA_VERSION, RiskCalculation, RiskInput

_ZERO_TOLERANCE = 1e-15


def _kelly_fraction(probability: float, win_loss_ratio: float) -> float:
    """Return non-negative full Kelly fraction for a binary payoff model."""
    if not 0 <= probability <= 1:
        raise ValueError("probability must be in [0, 1]")
    if win_loss_ratio <= 0:
        raise ValueError("win_loss_ratio must be positive")
    fraction = probability - (1.0 - probability) / win_loss_ratio
    return 0.0 if fraction <= _ZERO_TOLERANCE else fraction


def calculate_risk(request: RiskInput) -> RiskCalculation:
    """Calculate research-only risk sizing from a validated probability.

    The engine deliberately does not decide whether a trade should be opened.
    It computes a mathematically constrained risk amount. If ``risk_per_unit``
    is supplied, a notional unit count is also returned.
    """
    request.validate()
    ratio = request.trade_statistics.win_loss_ratio
    full_kelly = _kelly_fraction(request.probability, ratio)
    fractional_kelly = full_kelly * request.risk_policy.fractional_kelly
    final_fraction = min(
        fractional_kelly,
        request.risk_policy.max_risk_fraction,
    )
    risk_amount = request.account_equity * final_fraction

    position_size = None
    if request.risk_per_unit is not None:
        position_size = risk_amount / request.risk_per_unit
        max_notional = request.account_equity * request.risk_policy.max_position_fraction
        position_size = min(position_size, max_notional / request.risk_per_unit)

    return RiskCalculation(
        schema_version=RISK_SCHEMA_VERSION,
        asset=request.asset,
        direction=request.direction,
        probability=request.probability,
        win_loss_ratio=ratio,
        full_kelly_fraction=full_kelly,
        fractional_kelly_fraction=fractional_kelly,
        final_risk_fraction=final_fraction,
        risk_amount=risk_amount,
        position_size=position_size,
        capped=final_fraction < fractional_kelly,
        status="CALCULATED",
        research_id=request.research_id,
        probability_method=request.probability_method,
        probability_calculation_version=request.probability_calculation_version,
        probability_calibration_status=request.probability_calibration_status,
    )
