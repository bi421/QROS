"""Contract tests for the additive XAUUSD research orchestration layer."""

from datetime import datetime, timedelta, timezone

import pytest

from researchos.orchestration.xauusd_research import (
    EngineResult,
    EngineStatus,
    EvidenceRecord,
    OutcomeSpec,
    ResearchStatus,
    XAUUSDResearchError,
    XAUUSDResearchInputs,
    XAUUSDResearchOrchestrator,
    XAUUSDResearchRequest,
)

NOW = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)


def request(**overrides):
    values = {
        "run_id": "run-001",
        "instrument": "XAUUSD",
        "decision_time": NOW,
        "dataset_version": "sha256:dataset",
        "config_version": "xauusd-fusion-v1",
    }
    values.update(overrides)
    return XAUUSDResearchRequest(**values)


def evidence(engine="technical", **overrides):
    values = {
        "evidence_id": f"{engine}-evidence-1",
        "engine_name": engine,
        "instrument": "XAUUSD",
        "as_of": NOW - timedelta(minutes=15),
        "timeframe": "M15",
        "feature_name": "trend_direction",
        "value": 1,
        "direction": 1,
        "strength": 0.7,
        "quality": 1.0,
        "dependency_group": "price-derived",
    }
    values.update(overrides)
    return EvidenceRecord(**values)


def ok_adapter(name, record=None):
    record = record or evidence(engine=name)
    return lambda _request, _snapshot: EngineResult(
        engine_name=name, status=EngineStatus.OK, evidence=(record,)
    )


def test_request_is_xauusd_m15_with_canonical_context_timeframes():
    req = request()
    assert req.instrument == "XAUUSD"
    assert req.decision_timeframe == "M15"
    assert req.context_timeframes == ("M30", "H1", "H4", "D1")


@pytest.mark.parametrize("instrument", ["EURUSD", "XAUUSD.r", ""])
def test_rejects_non_xauusd_instrument(instrument):
    with pytest.raises(XAUUSDResearchError, match="XAUUSD only"):
        request(instrument=instrument)


def test_rejects_naive_decision_timestamp():
    with pytest.raises(XAUUSDResearchError, match="timezone-aware"):
        request(decision_time=datetime(2026, 10, 12, 8, 0))


def test_rejects_invalid_outcome_parameters():
    with pytest.raises(XAUUSDResearchError, match="take_profit_atr"):
        OutcomeSpec(take_profit_atr=float("inf"))


@pytest.mark.parametrize(
    ("field", "value"),
    [("atr_period", 1.5), ("atr_period", True), ("max_holding_bars", 2.5),
     ("max_holding_bars", False), ("take_profit_atr", True), ("stop_loss_atr", False)],
)
def test_outcome_spec_rejects_wrong_numeric_types(field, value):
    with pytest.raises(XAUUSDResearchError):
        OutcomeSpec(**{field: value})


def test_evidence_rejects_future_timeframe_and_invalid_probability_like_strength():
    with pytest.raises(XAUUSDResearchError, match="unsupported evidence timeframe"):
        evidence(timeframe="M5")
    with pytest.raises(XAUUSDResearchError, match="strength"):
        evidence(strength=1.1)


def test_valid_engines_are_collected_in_stable_name_order():
    orchestrator = XAUUSDResearchOrchestrator(
        {"technical": ok_adapter("technical"), "macro": ok_adapter("macro")}
    )
    result = orchestrator.run(request(), {"snapshot": "frozen"})
    assert result.status is ResearchStatus.EVIDENCE_COLLECTED
    assert [item.engine_name for item in result.engine_results] == ["macro", "technical"]
    assert [item.evidence_id for item in result.evidence] == [
        "macro-evidence-1",
        "technical-evidence-1",
    ]


def test_missing_required_engine_fails_closed():
    orchestrator = XAUUSDResearchOrchestrator(
        {"technical": ok_adapter("technical")},
        required_engines=("macro", "technical"),
    )
    result = orchestrator.run(request(), {})
    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
    assert result.missing_required_engines == ("macro",)
    assert "REQUIRED_ENGINE_NOT_CONFIGURED:macro" in result.reason_codes


def test_adapter_exception_is_recorded_and_required_engine_fails_closed():
    def broken(_request, _snapshot):
        raise RuntimeError("private details should not leak")

    result = XAUUSDResearchOrchestrator(
        {"technical": broken}, required_engines=("technical",)
    ).run(request(), {})
    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
    assert result.engine_results[0].status is EngineStatus.FAILED
    assert result.engine_results[0].reason_codes == (
        "ADAPTER_CONTRACT_FAILED:RuntimeError",
    )


def test_future_evidence_is_rejected_and_not_counted():
    future = evidence(as_of=NOW + timedelta(seconds=1))
    result = XAUUSDResearchOrchestrator(
        {"technical": ok_adapter("technical", future)},
        required_engines=("technical",),
    ).run(request(), {})
    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
    assert result.evidence == ()
    assert "ADAPTER_CONTRACT_FAILED:XAUUSDResearchError" in result.reason_codes


def test_duplicate_evidence_ids_fail_closed():
    shared = evidence(engine="macro", evidence_id="duplicate")
    orchestrator = XAUUSDResearchOrchestrator(
        {"macro": ok_adapter("macro", shared), "technical": ok_adapter(
            "technical", evidence(engine="technical", evidence_id="duplicate")
        )}
    )
    result = orchestrator.run(request(), {})
    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
    assert result.evidence == ()
    assert "DUPLICATE_EVIDENCE_ID" in result.reason_codes


def test_report_does_not_fabricate_probabilities_or_enable_execution():
    result = XAUUSDResearchOrchestrator(
        {"technical": ok_adapter("technical")}
    ).run(request(), {})
    payload = result.to_dict()
    assert payload["probabilities"] is None
    assert payload["execution_enabled"] is False
    assert payload["status"] == "EVIDENCE_COLLECTED"


def test_non_ok_engine_cannot_publish_evidence():
    def invalid(_request, _snapshot):
        return EngineResult(
            engine_name="technical",
            status=EngineStatus.FAILED,
            evidence=(evidence(),),
        )

    result = XAUUSDResearchOrchestrator(
        {"technical": invalid}, required_engines=("technical",)
    ).run(request(), {})
    assert result.status is ResearchStatus.INSUFFICIENT_EVIDENCE
    assert result.evidence == ()



def test_per_engine_inputs_route_distinct_snapshots_without_breaking_shared_snapshot_mode():
    seen = {}

    def capture(name):
        def adapter(_request, snapshot):
            seen[name] = snapshot
            return EngineResult(
                engine_name=name,
                status=EngineStatus.OK,
                evidence=(evidence(engine=name),),
            )
        return adapter

    market = object()
    macro = object()
    inputs = XAUUSDResearchInputs(
        default_snapshot=market,
        by_engine={"macro": macro},
    )
    result = XAUUSDResearchOrchestrator(
        {"technical": capture("technical"), "macro": capture("macro")}
    ).run(request(), inputs)

    assert result.status is ResearchStatus.EVIDENCE_COLLECTED
    assert seen["technical"] is market
    assert seen["macro"] is macro


def test_per_engine_inputs_fall_back_to_default_for_unlisted_engines():
    default = object()
    inputs = XAUUSDResearchInputs(default_snapshot=default, by_engine={"macro": object()})
    assert inputs.for_engine("technical") is default
