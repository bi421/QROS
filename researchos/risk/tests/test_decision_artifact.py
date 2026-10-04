from researchos.risk.contracts import RiskCalculation
from researchos.risk.decision_artifact import RiskDecisionArtifact
from researchos.risk.governance import RiskAccountState, RiskLimits, StrategyRiskState, evaluate_pretrade_risk

def _risk() -> RiskCalculation:
    return RiskCalculation(
        schema_version="risk.v1",
        asset="XAUUSD",
        direction="LONG",
        probability=0.70,
        win_loss_ratio=2.0,
        full_kelly_fraction=0.55,
        fractional_kelly_fraction=0.1375,
        final_risk_fraction=0.0025,
        risk_amount=25.0,
        position_size=1.0,
        capped=False,
        status="CALCULATED",
        assessment_hash="assessment-1",
        probability_method="weighted-evidence",
        probability_calculation_version="PROBABILITY_V1",
    )

def _decision(risk: RiskCalculation):
    return evaluate_pretrade_risk(
        risk,
        account=RiskAccountState(
            day_start_equity=10000.0,
            current_equity=10000.0,
            high_water_mark=10000.0,
            strategy_reference_equity=10000.0,
        ),
        limits=RiskLimits(),
        proposed_notional=1000.0,
        strategy_state=StrategyRiskState.RISK_REVIEW,
        research_valid=True,
    )

def test_risk_artifact_requires_full_provenance() -> None:
    import pytest
    risk = _risk()
    decision = _decision(risk)
    with pytest.raises(ValueError, match="assessment_hash"):
        RiskDecisionArtifact.build(
            RiskCalculation(**{**risk.__dict__, "assessment_hash": ""}),
            decision,
            "report-1",
        )

def test_risk_artifact_golden_path_and_tamper_detection() -> None:
    risk = _risk()
    decision = _decision(risk)
    artifact = RiskDecisionArtifact.build(risk, decision, "report-1")
    assert artifact.verify()
    restored = RiskDecisionArtifact.from_dict(artifact.to_dict())
    assert restored == artifact
    replayed = RiskDecisionArtifact.from_dict(restored.to_dict())
    assert replayed == artifact

    import pytest
    tampered = {**artifact.to_dict(), "report_hash": "report-2"}
    with pytest.raises(ValueError, match="hash"):
        RiskDecisionArtifact.from_dict(tampered)


def test_risk_artifact_rejects_unsupported_version_even_with_matching_hash() -> None:
    import pytest
    from researchos.core.identity import deterministic_hash

    risk = _risk()
    decision = _decision(risk)
    artifact = RiskDecisionArtifact.build(risk, decision, "report-1")
    payload = {**artifact.to_dict(), "artifact_version": "RISK_DECISION_ARTIFACT_V999"}
    payload["artifact_hash"] = deterministic_hash({k: v for k, v in payload.items() if k != "artifact_hash"})
    with pytest.raises(ValueError, match="hash"):
        RiskDecisionArtifact.from_dict(payload)
