"""Tests for the composite XAUUSD research input router."""

from datetime import datetime, timezone

from researchos.orchestration.xauusd_macro_adapter import (
    MacroDriverObservation,
    XAUUSDMacroSnapshot,
)
from researchos.macro.engine import ALL_DRIVERS
from researchos.orchestration.xauusd_research import (
    EngineStatus,
    OutcomeSpec,
    ResearchStatus,
    XAUUSDResearchRequest,
)
from researchos.orchestration.xauusd_research_inputs import (
    XAUUSDResearchInputs,
    build_xauusd_research_orchestrator,
    collect_xauusd_research,
)

NOW = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)


def request():
    return XAUUSDResearchRequest(
        run_id="composite-run-1",
        instrument="XAUUSD",
        decision_time=NOW,
        dataset_version="sha256:market-data",
        config_version="xauusd-fusion-v1",
        outcome_spec=OutcomeSpec(),
    )


def macro_snapshot():
    observations = tuple(
        MacroDriverObservation(
            driver_name=name,
            score=60.0,
            confidence=0.75,
            gold_impact_direction=1,
            as_of=NOW,
            source_refs=(f"source:{name}",),
            max_age_seconds=3600,
        )
        for name in ALL_DRIVERS
    )
    return XAUUSDMacroSnapshot(provider_id="macro-test-v1", observations=observations)


def test_missing_inputs_fail_closed_for_all_required_engines():
    result = collect_xauusd_research(request(), XAUUSDResearchInputs())
    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
    assert result.evidence == ()
    assert result.missing_required_engines == ("macro", "quant_math", "technical")
    assert "XAUUSD_MARKET_SNAPSHOT_NOT_CONFIGURED" in result.reason_codes
    assert "XAUUSD_MACRO_SNAPSHOT_NOT_CONFIGURED" in result.reason_codes


def test_macro_only_inputs_do_not_claim_complete_research():
    result = collect_xauusd_research(
        request(),
        XAUUSDResearchInputs(macro=macro_snapshot()),
    )
    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
    assert result.evidence
    assert {item.engine_name for item in result.evidence} == {"macro"}
    assert result.missing_required_engines == ("quant_math", "technical")
    assert result.to_dict()["probabilities"] is None
    assert result.to_dict()["execution_enabled"] is False


def test_unconfigured_macro_can_be_optional_but_is_still_reported():
    result = collect_xauusd_research(
        request(),
        XAUUSDResearchInputs(),
        required_engines=("technical", "quant_math"),
    )
    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
    assert result.missing_required_engines == ("quant_math", "technical")
    assert any(reason.startswith("OPTIONAL_ENGINE_NOT_CONFIGURED:macro") for reason in result.reason_codes)


def test_default_registry_declares_three_expected_engines():
    orchestrator = build_xauusd_research_orchestrator()
    result = orchestrator.run(request(), object())
    assert {item.engine_name for item in result.engine_results} == {"macro", "quant_math", "technical"}
    assert all(item.status is EngineStatus.NOT_CONFIGURED for item in result.engine_results)
    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
