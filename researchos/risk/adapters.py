"""Adapters from ResearchOS Block 2 probability outputs to ``risk.v1``."""

from __future__ import annotations

from typing import Any

from researchos.decision_engine.probability import ProbabilityAssessment, ProbabilityValidator
from researchos.risk.contracts import RiskInput, RiskPolicy, TradeStatistics


_DIRECTION_FIELDS = {
    "bullish": "bullish_probability",
    "bearish": "bearish_probability",
}


def risk_input_from_probability(
    assessment: ProbabilityAssessment | dict[str, Any],
    *,
    asset: str,
    direction: str,
    account_equity: float,
    trade_statistics: TradeStatistics,
    risk_policy: RiskPolicy = RiskPolicy(),
    risk_per_unit: float | None = None,
    probability_calibration_status: str | None = None,
) -> RiskInput:
    """Translate one validated Block 2 assessment into the ``risk.v1`` input.

    The adapter deliberately requires the caller to select a directional
    outcome. Neutral is not silently converted into a trade direction, and the
    adapter does not alter, normalize, or manufacture the probability.

    Calibration status is optional and must come from an external
    evidence-backed calibration evaluation. It is therefore passed explicitly
    at this boundary rather than inferred from probability magnitude.

    ``ProbabilityAssessment`` is accepted directly for in-process use or as a
    serialized dictionary for an API-first boundary. When a calibration status
    is explicitly supplied, it takes precedence over serialized metadata;
    otherwise the serialized ``probability_calibration_status`` value is
    preserved.
    """
    if isinstance(assessment, ProbabilityAssessment):
        normalized_assessment = assessment
    else:
        normalized_assessment = ProbabilityAssessment.from_dict(dict(assessment))
    normalized_assessment.validate_integrity()
    validation_errors = ProbabilityValidator().validate(normalized_assessment)
    if validation_errors:
        raise ValueError("invalid probability assessment: " + "; ".join(validation_errors))
    data = normalized_assessment.to_dict()
    normalized_direction = direction.strip().lower()

    try:
        probability_field = _DIRECTION_FIELDS[normalized_direction]
    except KeyError as exc:
        raise ValueError("direction must be 'bullish' or 'bearish'") from exc

    if "decision_context_id" not in data:
        raise ValueError("probability assessment is missing decision_context_id")
    if "assessment_hash" not in data:
        raise ValueError("probability assessment is missing assessment_hash")

    probability = float(data[probability_field])
    probability_method = str(data.get("calculation_method", "")) or None
    calibration_status = (
        probability_calibration_status
        if probability_calibration_status is not None
        else data.get("probability_calibration_status")
    )

    if calibration_status is not None and not str(calibration_status).strip():
        raise ValueError("probability_calibration_status must be non-empty when provided")

    request = RiskInput(
        asset=asset,
        direction=normalized_direction,
        probability=probability,
        account_equity=account_equity,
        trade_statistics=trade_statistics,
        risk_policy=risk_policy,
        risk_per_unit=risk_per_unit,
        research_id=str(data["decision_context_id"]),
        probability_method=probability_method,
        probability_calculation_version=normalized_assessment.calculation_version,
        probability_calibration_status=(
            str(calibration_status) if calibration_status is not None else None
        ),
        assessment_hash=normalized_assessment.assessment_hash,
    )
    request.validate()
    return request
