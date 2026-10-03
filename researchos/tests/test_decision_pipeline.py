from researchos.decision_engine.probability import ProbabilityAssessment
from researchos.decision_pipeline import DecisionPipelineInput, run_decision_pipeline
from researchos.risk.contracts import RiskAccountSnapshot, TradeStatistics


def _assessment(*, calibration_status: str | None = None) -> ProbabilityAssessment:
    return ProbabilityAssessment(
        decision_context_id="research-001",
        evidence_collection_id="evidence-001",
        bullish_probability=0.60,
        bearish_probability=0.25,
        neutral_probability=0.15,
        confidence=0.80,
        uncertainty=0.40,
        evidence_strength=0.70,
        historical_consistency=0.60,
        sample_size=20,
        probability_calibration_status=calibration_status,
    )


def _account() -> RiskAccountSnapshot:
    return RiskAccountSnapshot.flat(10_000.0)


def test_pipeline_produces_human_review_report_with_risk_gate() -> None:
    report = run_decision_pipeline(
        DecisionPipelineInput(
            assessment=_assessment(),
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
            risk_per_unit=20,
        )
    )
    assert report.schema_version == "pretrade.v2"
    assert report.status == "READY_FOR_HUMAN_REVIEW"
    assert report.risk_gate_status == "RESEARCH_ONLY"
    assert report.execution_allowed is False
    assert report.probability == 0.60
    assert report.risk_amount > 0
    assert report.position_size is not None
    assert report.research_id == "research-001"


def test_pipeline_fails_closed_when_risk_account_context_is_missing() -> None:
    report = run_decision_pipeline(
        DecisionPipelineInput(
            assessment=_assessment(),
            asset="XAUUSD",
            direction="bullish",
            account_equity=10_000,
            trade_statistics=TradeStatistics(average_win=150, average_loss=100),
            research_valid=True,
            strategy_id="strategy-001",
        )
    )
    assert report.status == "BLOCKED_RISK_GATE"
    assert report.risk_valid is False
    assert "RISK_ACCOUNT_CONTEXT_MISSING" in report.risk_hard_failures


def test_pipeline_blocks_invalid_research() -> None:
    report = run_decision_pipeline(
        DecisionPipelineInput(
            assessment=_assessment(),
            asset="XAUUSD",
            direction="bullish",
            account_equity=10_000,
            trade_statistics=TradeStatistics(average_win=150, average_loss=100),
            research_valid=False,
            risk_account=_account(),
            strategy_id="strategy-001",
            research_limitations=("validation pending",),
        )
    )
    assert report.status == "BLOCKED_RESEARCH_VALIDATION"
    assert report.risk_valid is True
    assert report.limitations == ("validation pending",)


def test_pipeline_accepts_serialized_probability_boundary() -> None:
    data = _assessment().to_dict()
    report = run_decision_pipeline(
        DecisionPipelineInput(
            assessment=data,
            asset="XAUUSD",
            direction="bearish",
            account_equity=10_000,
            trade_statistics=TradeStatistics(average_win=100, average_loss=100),
            research_valid=True,
            risk_account=_account(),
            strategy_id="strategy-001",
        )
    )
    assert report.direction == "bearish"
    assert report.probability == 0.25


def test_pipeline_propagates_evidence_backed_calibration_status() -> None:
    report = run_decision_pipeline(
        DecisionPipelineInput(
            assessment=_assessment(calibration_status="Well-Calibrated"),
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
        )
    )
    assert report.risk_valid is True
    assert report.probability == 0.60


def test_probability_calibration_status_round_trips_through_serialization() -> None:
    assessment = _assessment(calibration_status="Poorly Calibrated")
    restored = ProbabilityAssessment.from_dict(assessment.to_dict())
    assert restored.probability_calibration_status == "Poorly Calibrated"
    assert restored.assessment_hash == assessment.assessment_hash

    report = run_decision_pipeline(
        DecisionPipelineInput(
            assessment=restored,
            asset="XAUUSD",
            direction="bullish",
            account_equity=10_000,
            trade_statistics=TradeStatistics(
                average_win=150,
                average_loss=100,
            ),
            research_valid=True,
            risk_account=_account(),
            strategy_id="strategy-001",
        )
    )
    assert report.probability == 0.60
