from __future__ import annotations

from researchos.action.report import build_pre_trade_report
from researchos.decision_engine.probability import ProbabilityAssessment
from researchos.decision_pipeline import DecisionPipelineInput, run_decision_pipeline
from researchos.risk.adapters import risk_input_from_probability
from researchos.risk.contracts import RiskAccountSnapshot, RiskPolicy, TradeStatistics
from researchos.risk.engine import calculate_risk


def _assessment(status: str | None = None) -> ProbabilityAssessment:
    return ProbabilityAssessment(
        decision_context_id="contract-research-001",
        evidence_collection_id="contract-evidence-001",
        bullish_probability=0.60,
        bearish_probability=0.25,
        neutral_probability=0.15,
        confidence=0.80,
        uncertainty=0.40,
        evidence_strength=0.70,
        historical_consistency=0.60,
        sample_size=20,
        probability_calibration_status=status,
    )


def _account() -> RiskAccountSnapshot:
    return RiskAccountSnapshot.flat(10_000.0)


def test_calibration_status_survives_probability_risk_pretrade_boundary() -> None:
    assessment = _assessment("Well-Calibrated")
    risk_input = risk_input_from_probability(
        assessment,
        asset="XAUUSD",
        direction="bullish",
        account_equity=10_000,
        trade_statistics=TradeStatistics(
            average_win=150,
            average_loss=100,
            sample_size=100,
        ),
    )

    assert risk_input.probability_calibration_status == "Well-Calibrated"

    report = run_decision_pipeline(
        DecisionPipelineInput(
            assessment=assessment,
            asset="XAUUSD",
            direction="bullish",
            account_equity=10_000,
            trade_statistics=TradeStatistics(
                average_win=150,
                average_loss=100,
                sample_size=100,
            ),
            research_valid=True,
            risk_account=_account(),
            strategy_id="strategy-001",
            risk_policy=RiskPolicy(
                max_risk_fraction=0.005,
                max_loss_per_trade_fraction=0.005,
            ),
        )
    )
    assert report.status == "READY_FOR_HUMAN_REVIEW"
    assert report.risk_gate_status == "RESEARCH_ONLY"
    assert report.probability == assessment.bullish_probability


def test_serialized_assessment_preserves_contract_across_boundary() -> None:
    assessment = _assessment("Poorly Calibrated")
    serialized = assessment.to_dict()
    restored = ProbabilityAssessment.from_dict(serialized)

    assert restored.assessment_hash == assessment.assessment_hash
    assert restored.probability_calibration_status == "Poorly Calibrated"

    risk_input = risk_input_from_probability(
        serialized,
        asset="XAUUSD",
        direction="bullish",
        account_equity=10_000,
        trade_statistics=TradeStatistics(average_win=150, average_loss=100),
    )
    assert risk_input.probability_calibration_status == "Poorly Calibrated"


def test_invalid_research_never_becomes_trade_ready() -> None:
    report = run_decision_pipeline(
        DecisionPipelineInput(
            assessment=_assessment("Well-Calibrated"),
            asset="XAUUSD",
            direction="bullish",
            account_equity=10_000,
            trade_statistics=TradeStatistics(average_win=150, average_loss=100),
            research_valid=False,
            risk_account=_account(),
            strategy_id="strategy-001",
            risk_policy=RiskPolicy(
                max_risk_fraction=0.005,
                max_loss_per_trade_fraction=0.005,
            ),
            research_limitations=("research evidence not validated",),
        )
    )
    assert report.status == "BLOCKED_RESEARCH_VALIDATION"
    assert report.research_valid is False
    assert report.risk_valid is True


def test_zero_risk_budget_never_becomes_trade_ready() -> None:
    risk_input = risk_input_from_probability(
        _assessment(),
        asset="XAUUSD",
        direction="bullish",
        account_equity=10_000,
        trade_statistics=TradeStatistics(average_win=100, average_loss=100),
        risk_policy=RiskPolicy(
            fractional_kelly=0.25,
            max_risk_fraction=0.0,
            max_position_fraction=1.0,
        ),
    )
    report = build_pre_trade_report(
        calculate_risk(risk_input),
        research_valid=True,
    )
    assert report.status == "NO_POSITIVE_RISK_BUDGET"
