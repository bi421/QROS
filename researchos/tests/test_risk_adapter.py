from researchos.decision_engine.probability import ProbabilityAssessment
from researchos.risk.adapters import risk_input_from_probability
from researchos.risk.contracts import RiskPolicy, TradeStatistics


def _assessment() -> ProbabilityAssessment:
    return ProbabilityAssessment(
        decision_context_id="ctx-xauusd-001",
        evidence_collection_id="evidence-001",
        bullish_probability=0.60,
        bearish_probability=0.25,
        neutral_probability=0.15,
        confidence=0.80,
        uncertainty=0.40,
        evidence_strength=0.55,
        historical_consistency=0.60,
        sample_size=20,
    )


def test_probability_assessment_maps_to_risk_input() -> None:
    request = risk_input_from_probability(
        _assessment(),
        asset="XAUUSD",
        direction="bullish",
        account_equity=10_000,
        trade_statistics=TradeStatistics(
            average_win=150,
            average_loss=100,
            sample_size=100,
        ),
    )

    assert request.probability == 0.60
    assert request.direction == "bullish"
    assert request.research_id == "ctx-xauusd-001"
    assert request.probability_method == "WeightedEvidence"
    assert request.probability_calibration_status is None
    assert request.to_dict()["schema_version"] == "risk.v2"


def test_serialized_probability_assessment_crosses_same_boundary() -> None:
    request = risk_input_from_probability(
        _assessment().to_dict(),
        asset="XAUUSD",
        direction="bearish",
        account_equity=10_000,
        trade_statistics=TradeStatistics(
            average_win=100,
            average_loss=100,
            sample_size=100,
        ),
        risk_policy=RiskPolicy(fractional_kelly=0.25, max_risk_fraction=0.01),
    )

    assert request.probability == 0.25
    assert request.direction == "bearish"
    assert request.research_id == "ctx-xauusd-001"


def test_explicit_calibration_status_crosses_probability_to_risk_boundary() -> None:
    request = risk_input_from_probability(
        _assessment(),
        asset="XAUUSD",
        direction="bullish",
        account_equity=10_000,
        trade_statistics=TradeStatistics(
            average_win=150,
            average_loss=100,
            sample_size=100,
        ),
        probability_calibration_status="Well-Calibrated",
    )

    assert request.probability_calibration_status == "Well-Calibrated"
    assert request.to_dict()["probability_calibration_status"] == "Well-Calibrated"


def test_empty_calibration_status_is_rejected() -> None:
    try:
        risk_input_from_probability(
            _assessment(),
            asset="XAUUSD",
            direction="bullish",
            account_equity=10_000,
            trade_statistics=TradeStatistics(average_win=150, average_loss=100),
            probability_calibration_status="   ",
        )
    except ValueError as exc:
        assert "probability_calibration_status" in str(exc)
    else:
        raise AssertionError("blank calibration status must be rejected")


def test_neutral_probability_cannot_be_silently_traded() -> None:
    try:
        risk_input_from_probability(
            _assessment(),
            asset="XAUUSD",
            direction="neutral",
            account_equity=10_000,
            trade_statistics=TradeStatistics(average_win=100, average_loss=100),
        )
    except ValueError as exc:
        assert "bullish" in str(exc)
        assert "bearish" in str(exc)
    else:
        raise AssertionError(
            "neutral direction must not cross the trading risk boundary"
        )
