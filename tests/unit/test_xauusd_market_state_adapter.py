from datetime import datetime, timezone

from researchos.orchestration.xauusd_market_state_adapter import (
    XAUUSDMarketStateEvidenceAdapter,
)
from researchos.orchestration.xauusd_research import (
    EngineStatus,
    XAUUSDResearchRequest,
)


def _request() -> XAUUSDResearchRequest:
    return XAUUSDResearchRequest(
        run_id="run-1",
        instrument="XAUUSD",
        decision_time=datetime.fromtimestamp(1_800_000_000, tz=timezone.utc),
        dataset_version="dataset-v1",
        config_version="config-v1",
    )


def _clock(source: str) -> dict:
    return {
        "source": source,
        "event_age_ms": 10.0,
        "ingest_age_ms": 5.0,
        "transport_ms": 5.0,
        "clock_skew_suspected": False,
        "fresh": True,
    }


def _state() -> dict:
    request = _request()
    return {
        "instrument": "XAUUSD",
        "decision_time_ns": int(request.decision_time.timestamp() * 1_000_000_000),
        "status": "READY_FOR_FUSION",
        "features": {
            "broker_quote": {
                "status": "OK", "mid_price": 2650.0, "spread": 0.2,
                "spread_bps": 0.75, "top_size_imbalance": 0.25,
                "clock": _clock("broker-demo"),
            },
            "futures_order_book": {
                "status": "OK", "bid_depth": 12.0, "ask_depth": 8.0,
                "depth_imbalance": 0.2, "clock": _clock("cme-demo"),
            },
            "futures_trade_flow": {
                "status": "OK", "total_volume": 100.0, "signed_volume": 20.0,
                "signed_volume_imbalance": 0.2, "clock": _clock("cme-trades-demo"),
            },
            "macro": {
                "DXY": {"status": "OK", "value": 101.2, "return_since_previous": -0.001,
                        "clock": _clock("dxy-demo")},
                "VXY": {"status": "OK", "value": 19.0, "return_since_previous": 0.02,
                        "clock": _clock("vxy-demo")},
            },
        },
        "probabilities": None,
        "probability_status": "NOT_CALIBRATED",
        "execution_enabled": False,
    }


def test_complete_fresh_state_becomes_timestamped_evidence():
    result = XAUUSDMarketStateEvidenceAdapter()(_request(), _state())

    assert result.status == EngineStatus.OK
    assert result.engine_name == "market_state"
    assert result.evidence
    assert all(item.as_of <= _request().decision_time for item in result.evidence)
    assert any(item.feature_name == "DXY_return_since_previous" for item in result.evidence)
    assert all(item.source_refs for item in result.evidence)


def test_stale_required_source_fails_closed_without_partial_evidence():
    state = _state()
    state["features"]["futures_order_book"]["status"] = "STALE"

    result = XAUUSDMarketStateEvidenceAdapter()(_request(), state)

    assert result.status == EngineStatus.INSUFFICIENT
    assert result.evidence == ()
    assert "SOURCE_NOT_READY:futures_order_book:default" in result.reason_codes


def test_future_event_time_is_rejected_without_partial_evidence():
    state = _state()
    state["features"]["broker_quote"]["clock"]["event_age_ms"] = -1.0

    result = XAUUSDMarketStateEvidenceAdapter()(_request(), state)

    assert result.status == EngineStatus.INSUFFICIENT
    assert result.evidence == ()
    assert "SOURCE_CLOCK_INVALID:broker_quote:default" in result.reason_codes


def test_decision_timestamp_mismatch_is_rejected():
    state = _state()
    state["decision_time_ns"] += 10_000_000

    result = XAUUSDMarketStateEvidenceAdapter()(_request(), state)

    assert result.status == EngineStatus.INSUFFICIENT
    assert result.evidence == ()
    assert result.reason_codes == ("DECISION_TIMESTAMP_MISMATCH",)
