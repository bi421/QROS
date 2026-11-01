from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from researchos.quant_engine.order_flow.contracts import (
    AggressorMethod,
    AggressorSide,
    QuoteCondition,
    QuoteEvent,
    TradeEvent,
)
from researchos.quant_engine.order_flow.features import (
    TradeClassification,
    aggregate_trade_flow,
    classify_trade,
    compute_cvd,
    price_progress_ticks,
)

NOW = datetime(2026, 11, 2, 4, 0, tzinfo=timezone.utc)
HASH = "a" * 64


def instrument():
    from researchos.quant_engine.order_flow.contracts import InstrumentMetadata

    return InstrumentMetadata(
        instrument_id="GCZ6",
        instrument_root="GC",
        contract_month="202612",
        currency="USD",
        tick_size=Decimal("0.1"),
        tick_value=Decimal("10"),
        multiplier=Decimal("100"),
    )


def trade(**overrides):
    values = {
        "source_id": "synthetic-feed",
        "dataset_id": "synthetic-v1",
        "instrument_id": "GCZ6",
        "event_time_utc": NOW,
        "receive_time_utc": NOW + timedelta(milliseconds=2),
        "price": Decimal("2400.1"),
        "quantity": Decimal("3"),
        "raw_event_hash": HASH,
    }
    values.update(overrides)
    return TradeEvent(**values)


def quote(**overrides):
    values = {
        "source_id": "synthetic-feed",
        "dataset_id": "synthetic-v1",
        "instrument_id": "GCZ6",
        "event_time_utc": NOW - timedelta(milliseconds=1),
        "receive_time_utc": NOW - timedelta(milliseconds=1),
        "bid_price": Decimal("2400.0"),
        "ask_price": Decimal("2400.1"),
        "raw_event_hash": HASH,
    }
    values.update(overrides)
    return QuoteEvent(**values)


def test_exchange_aggressor_flag_has_priority_and_is_not_relabelled() -> None:
    item = trade(aggressor_side=AggressorSide.BUY, aggressor_method=AggressorMethod.EXCHANGE_FLAG)
    result = classify_trade(item, [quote()], max_quote_age=timedelta(seconds=1))
    assert result.side == AggressorSide.BUY
    assert result.method == AggressorMethod.EXCHANGE_FLAG
    assert result.reason == "EXCHANGE_FLAG_PRESERVED"


def test_quote_inference_buy_sell_and_inside_spread_unknown() -> None:
    prior = quote()
    buy = classify_trade(
        trade(price=Decimal("2400.1")), [prior], max_quote_age=timedelta(seconds=1)
    )
    sell = classify_trade(
        trade(price=Decimal("2400.0")), [prior], max_quote_age=timedelta(seconds=1)
    )
    inside = classify_trade(
        trade(price=Decimal("2400.05")), [prior], max_quote_age=timedelta(seconds=1)
    )
    assert (buy.side, buy.method) == (AggressorSide.BUY, AggressorMethod.QUOTE_INFERRED)
    assert (sell.side, sell.method) == (AggressorSide.SELL, AggressorMethod.QUOTE_INFERRED)
    assert (inside.side, inside.method) == (AggressorSide.UNKNOWN, AggressorMethod.UNKNOWN)


def test_quote_inference_fails_closed_for_missing_stale_or_noncausal_quote() -> None:
    item = trade()
    missing = classify_trade(item, [], max_quote_age=timedelta(seconds=1))
    stale_quote = quote(
        event_time_utc=NOW - timedelta(seconds=5), receive_time_utc=NOW - timedelta(seconds=4)
    )
    stale = classify_trade(item, [stale_quote], max_quote_age=timedelta(seconds=1))
    future = quote(
        event_time_utc=NOW + timedelta(seconds=1), receive_time_utc=NOW + timedelta(seconds=2)
    )
    noncausal = classify_trade(item, [future], max_quote_age=timedelta(seconds=5))
    assert missing.side == AggressorSide.UNKNOWN
    assert missing.reason == "NO_CAUSAL_PRIOR_QUOTE"
    assert stale.reason == "STALE_QUOTE"
    assert noncausal.side == AggressorSide.UNKNOWN


def test_quote_inference_rejects_late_received_and_locked_quotes() -> None:
    item = trade()
    late = quote(
        event_time_utc=NOW - timedelta(milliseconds=1), receive_time_utc=NOW + timedelta(seconds=1)
    )
    locked = quote(
        event_time_utc=NOW - timedelta(milliseconds=1),
        receive_time_utc=NOW,
        bid_price=Decimal("2400.0"),
        ask_price=Decimal("2400.0"),
        condition=QuoteCondition.LOCKED,
    )
    assert (
        classify_trade(item, [late], max_quote_age=timedelta(seconds=1)).side
        == AggressorSide.UNKNOWN
    )
    assert (
        classify_trade(item, [locked], max_quote_age=timedelta(seconds=1)).side
        == AggressorSide.UNKNOWN
    )


def test_quote_inference_rejects_ambiguous_latest_quote_timestamp() -> None:
    first = quote()
    second = quote(raw_event_hash="b" * 64)
    result = classify_trade(trade(), [first, second], max_quote_age=timedelta(seconds=1))
    assert result.side == AggressorSide.UNKNOWN
    assert result.reason == "AMBIGUOUS_QUOTE_TIMESTAMP"


def test_delta_excludes_unknown_but_coverage_includes_unknown_quantity() -> None:
    q = quote()
    classifications = [
        classify_trade(
            trade(price=Decimal("2400.1"), quantity=Decimal("5")),
            [q],
            max_quote_age=timedelta(seconds=1),
        ),
        classify_trade(
            trade(price=Decimal("2400.0"), quantity=Decimal("2")),
            [q],
            max_quote_age=timedelta(seconds=1),
        ),
        classify_trade(
            trade(price=Decimal("2400.05"), quantity=Decimal("3")),
            [q],
            max_quote_age=timedelta(seconds=1),
        ),
        classify_trade(
            trade(
                price=Decimal("2400.1"),
                quantity=Decimal("4"),
                aggressor_side=AggressorSide.BUY,
                aggressor_method=AggressorMethod.EXCHANGE_FLAG,
            ),
            [q],
            max_quote_age=timedelta(seconds=1),
        ),
    ]
    flow = aggregate_trade_flow(
        classifications,
        instrument_id="GCZ6",
        session_id="RTH",
        start_utc=NOW - timedelta(seconds=1),
        end_utc=NOW + timedelta(seconds=1),
    )
    assert flow.buy_quantity == Decimal("9")
    assert flow.sell_quantity == Decimal("2")
    assert flow.unknown_quantity == Decimal("3")
    assert flow.delta == Decimal("7")
    assert flow.exchange_flag_delta == Decimal("4")
    assert flow.quote_inferred_delta == Decimal("3")
    assert flow.exchange_flag_buy_quantity == Decimal("4")
    assert flow.quote_inferred_buy_quantity == Decimal("5")
    assert flow.total_quantity == Decimal("14")
    assert flow.classified_coverage == Decimal("11") / Decimal("14")
    assert flow.trade_count == 4
    assert flow.unknown_trade_count == 1


def test_aggregation_uses_half_open_window_and_exact_instrument() -> None:
    q = quote()
    at_start = trade(
        event_time_utc=NOW - timedelta(seconds=1), receive_time_utc=NOW - timedelta(seconds=1)
    )
    at_end = trade(
        event_time_utc=NOW + timedelta(seconds=1), receive_time_utc=NOW + timedelta(seconds=1)
    )
    other = trade(instrument_id="MGCZ6")
    items = [
        classify_trade(at_start, [q], max_quote_age=timedelta(seconds=5)),
        classify_trade(at_end, [q], max_quote_age=timedelta(seconds=5)),
        classify_trade(other, [q], max_quote_age=timedelta(seconds=1)),
    ]
    flow = aggregate_trade_flow(
        items,
        instrument_id="GCZ6",
        session_id="RTH",
        start_utc=NOW - timedelta(seconds=1),
        end_utc=NOW + timedelta(seconds=1),
    )
    assert flow.trade_count == 1


def test_cvd_accumulates_within_session_and_resets_on_new_session() -> None:
    def classified_at(price: str, quantity: str, at: datetime):
        prior = quote(
            event_time_utc=at - timedelta(milliseconds=1),
            receive_time_utc=at - timedelta(milliseconds=1),
        )
        item = trade(
            event_time_utc=at,
            receive_time_utc=at + timedelta(milliseconds=1),
            price=Decimal(price),
            quantity=Decimal(quantity),
        )
        return classify_trade(item, [prior], max_quote_age=timedelta(seconds=1))

    first = classified_at("2400.1", "5", NOW)
    second = classified_at("2400.0", "2", NOW + timedelta(seconds=1))
    third = classified_at("2400.1", "5", NOW + timedelta(seconds=2))
    one = aggregate_trade_flow(
        [first],
        instrument_id="GCZ6",
        session_id="RTH",
        start_utc=NOW,
        end_utc=NOW + timedelta(seconds=1),
    )
    two = aggregate_trade_flow(
        [second],
        instrument_id="GCZ6",
        session_id="RTH",
        start_utc=NOW + timedelta(seconds=1),
        end_utc=NOW + timedelta(seconds=2),
    )
    three = aggregate_trade_flow(
        [third],
        instrument_id="GCZ6",
        session_id="ETH",
        start_utc=NOW + timedelta(seconds=2),
        end_utc=NOW + timedelta(seconds=3),
    )
    points = compute_cvd([one, two, three])
    assert [point.cvd for point in points] == [Decimal("5"), Decimal("3"), Decimal("5")]


def test_cvd_rejects_out_of_order_or_overlapping_windows() -> None:
    empty = aggregate_trade_flow(
        [],
        instrument_id="GCZ6",
        session_id="RTH",
        start_utc=NOW,
        end_utc=NOW + timedelta(seconds=2),
    )
    overlap = aggregate_trade_flow(
        [],
        instrument_id="GCZ6",
        session_id="RTH",
        start_utc=NOW + timedelta(seconds=1),
        end_utc=NOW + timedelta(seconds=3),
    )
    with pytest.raises(ValueError, match="non-overlapping"):
        compute_cvd([empty, overlap])
    with pytest.raises(ValueError, match="non-overlapping"):
        compute_cvd([overlap, empty])


def test_price_progress_is_signed_and_tick_normalized() -> None:
    meta = instrument()
    assert price_progress_ticks(Decimal("2400.0"), Decimal("2400.3"), meta) == Decimal("3")
    assert price_progress_ticks(Decimal("2400.3"), Decimal("2400.0"), meta) == Decimal("-3")
    with pytest.raises(ValueError, match="tick_size"):
        price_progress_ticks(Decimal("2400.05"), Decimal("2400.1"), meta)


def test_invalid_max_quote_age_and_window_are_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        classify_trade(trade(), [quote()], max_quote_age=timedelta(0))
    with pytest.raises(ValueError, match="after"):
        aggregate_trade_flow([], instrument_id="GCZ6", session_id="RTH", start_utc=NOW, end_utc=NOW)


def test_same_timestamp_quote_and_stale_quote_are_not_used() -> None:
    same_time = quote(
        event_time_utc=NOW,
        receive_time_utc=NOW,
    )
    stale = quote(
        event_time_utc=NOW - timedelta(seconds=5),
        receive_time_utc=NOW - timedelta(seconds=5),
        condition=QuoteCondition.STALE,
    )
    same = classify_trade(trade(), [same_time], max_quote_age=timedelta(seconds=10))
    stale_result = classify_trade(trade(), [stale], max_quote_age=timedelta(seconds=10))
    assert same.side == AggressorSide.UNKNOWN
    assert same.reason == "NO_CAUSAL_PRIOR_QUOTE"
    assert stale_result.side == AggressorSide.UNKNOWN
    assert stale_result.reason == "QUOTE_CONDITION_STALE"


def test_trade_classification_rejects_inconsistent_side_and_method() -> None:
    with pytest.raises(ValueError, match="UNKNOWN method"):
        TradeClassification(trade(), AggressorSide.BUY, AggressorMethod.UNKNOWN, None, "bad")
    with pytest.raises(ValueError, match="classified method"):
        TradeClassification(
            trade(), AggressorSide.UNKNOWN, AggressorMethod.EXCHANGE_FLAG, None, "bad"
        )


def test_empty_flow_window_has_zero_delta_and_zero_coverage() -> None:
    flow = aggregate_trade_flow(
        [],
        instrument_id="GCZ6",
        session_id="RTH",
        start_utc=NOW,
        end_utc=NOW + timedelta(seconds=1),
    )
    assert flow.delta == Decimal("0")
    assert flow.classified_coverage == Decimal("0")
    assert flow.trade_count == 0
