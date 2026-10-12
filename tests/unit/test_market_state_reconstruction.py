"""Tests for the additive point-in-time market-state engine."""
from researchos.orchestration.market_state_reconstruction import (
    BookLevel, BookSnapshot, EventClock, MacroPoint, ParallelMarketStateEngine,
    Quote, SourcePolicy, TradePrint,
)
NOW = 1_800_000_000_000_000_000


def clock(source, age_ms=10, seq=1):
    event = NOW - int(age_ms * 1_000_000)
    return EventClock(source, event, event + 1_000_000, seq)


def test_parallel_engine_computes_quote_book_flow_and_macro_features():
    result = ParallelMarketStateEngine().reconstruct(
        symbol="XAUUSD", decision_time_ns=NOW,
        quotes=[Quote(clock("broker", 10), "XAUUSD", 2300.0, 2300.2, 12, 8)],
        books=[BookSnapshot(clock("COMEX", 12), "XAUUSD",
            (BookLevel(2300.0, 40), BookLevel(2299.9, 30)),
            (BookLevel(2300.2, 10), BookLevel(2300.3, 20)))],
        trades=[TradePrint(clock("COMEX", 15), "XAUUSD", 2300.2, 5, 1),
                TradePrint(clock("COMEX", 14, 2), "XAUUSD", 2300.0, 2, -1)],
        macro=[MacroPoint(clock("DXY-provider", 100), "DXY", 101.0),
               MacroPoint(clock("DXY-provider", 90), "DXY", 101.1),
               MacroPoint(clock("VXY-provider", 100), "VXY", 15.0)],
    )
    assert result["features"]["broker_quote"]["spread"] == 0.2
    assert result["features"]["futures_order_book"]["depth_imbalance"] > 0
    assert result["features"]["futures_trade_flow"]["signed_volume"] == 3
    assert result["features"]["macro"]["DXY"]["return_since_previous"] > 0
    assert result["probabilities"] is None
    assert result["execution_enabled"] is False


def test_missing_live_sources_fail_closed_and_are_not_fabricated():
    result = ParallelMarketStateEngine().reconstruct(symbol="XAUUSD", decision_time_ns=NOW)
    assert result["status"] == "PARTIAL_OR_STALE"
    assert result["features"]["broker_quote"]["status"] == "NOT_CONFIGURED"
    assert result["features"]["macro"]["DXY"]["status"] == "NOT_CONFIGURED"
    assert result["probability_status"] == "NOT_CALIBRATED"


def test_stale_quote_is_not_marked_ready():
    result = ParallelMarketStateEngine(quote_policy=SourcePolicy(max_age_ms=20)).reconstruct(
        symbol="XAUUSD", decision_time_ns=NOW,
        quotes=[Quote(clock("broker", 500), "XAUUSD", 2300.0, 2300.2)],
    )
    assert result["features"]["broker_quote"]["status"] == "STALE"
    assert result["status"] == "PARTIAL_OR_STALE"


def test_rejects_future_data_and_crossed_book():
    result = ParallelMarketStateEngine().reconstruct(
        symbol="XAUUSD", decision_time_ns=NOW,
        quotes=[Quote(EventClock("broker", NOW + 1, NOW + 2), "XAUUSD", 2300, 2300.2)],
    )
    assert result["features"]["broker_quote"]["status"] == "STALE"
    try:
        ParallelMarketStateEngine().reconstruct(
            symbol="XAUUSD", decision_time_ns=NOW,
            books=[BookSnapshot(clock("COMEX"), "XAUUSD",
                (BookLevel(2300.3, 1),), (BookLevel(2300.2, 1),))],
        )
    except ValueError as exc:
        assert "crossed" in str(exc)
    else:
        raise AssertionError("crossed book must fail closed")


def test_rejects_wrong_symbol_and_invalid_policy():
    try:
        ParallelMarketStateEngine().reconstruct(symbol="EURUSD", decision_time_ns=NOW)
    except ValueError as exc:
        assert "XAUUSD" in str(exc)
    else:
        raise AssertionError("unsupported symbol must be rejected")
    try:
        ParallelMarketStateEngine(quote_policy=SourcePolicy(max_age_ms=-1))
    except ValueError:
        pass
    else:
        raise AssertionError("invalid policy must be rejected")
