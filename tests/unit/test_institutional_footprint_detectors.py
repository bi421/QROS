from datetime import datetime, timedelta, timezone
from decimal import Decimal

from researchos.quant_engine.order_flow.contracts import AggressorMethod, AggressorSide, TradeEvent
from researchos.quant_engine.order_flow.features import FlowWindow, TradeClassification
from researchos.quant_engine.order_flow.detectors import (
    DetectorDefinition,
    FlowSource,
    FootprintState,
    ReferenceLevel,
    SizeReference,
    SweepObservation,
    classify_aggression_price_response,
    detect_absorption_candidate,
    detect_large_trade_clusters,
    detect_liquidity_sweep_candidate,
    detect_unusually_large_prints,
)

NOW = datetime(2026, 11, 2, 4, 0, tzinfo=timezone.utc)
HASH = "a" * 64


def classified(n: int, qty: str = "10", side=AggressorSide.BUY):
    at = NOW + timedelta(seconds=n)
    t = TradeEvent(
        "synthetic",
        "fixture",
        "GCZ6",
        at,
        at,
        Decimal("2400.0"),
        Decimal(qty),
        (hex(n + 1)[2:] * 64)[:64],
        side,
        AggressorMethod.UNKNOWN if side == AggressorSide.UNKNOWN else AggressorMethod.EXCHANGE_FLAG,
    )
    method = (
        AggressorMethod.UNKNOWN if side == AggressorSide.UNKNOWN else AggressorMethod.EXCHANGE_FLAG
    )
    return TradeClassification(t, side, method, None, "fixture")


def flow(*, ex_buy="10", ex_sell="0", quote_buy="0", quote_sell="0", unknown="0"):
    total = sum(map(Decimal, (ex_buy, ex_sell, quote_buy, quote_sell, unknown)), Decimal(0))
    return FlowWindow(
        "GCZ6",
        "RTH",
        NOW,
        NOW + timedelta(seconds=1),
        3,
        3,
        0,
        total,
        Decimal(ex_buy) + Decimal(quote_buy),
        Decimal(ex_sell) + Decimal(quote_sell),
        Decimal(unknown),
        Decimal(ex_buy),
        Decimal(ex_sell),
        Decimal(quote_buy),
        Decimal(quote_sell),
        Decimal(ex_buy) - Decimal(ex_sell),
        Decimal(quote_buy) - Decimal(quote_sell),
        Decimal(ex_buy) + Decimal(quote_buy) - Decimal(ex_sell) - Decimal(quote_sell),
        (total - Decimal(unknown)) / total if total else Decimal(0),
    )


def test_detector_definition_hash_is_stable_and_threshold_sensitive():
    a = DetectorDefinition()
    assert a.definition_id == DetectorDefinition().definition_id
    assert a.definition_id != DetectorDefinition(cluster_minimum_prints=4).definition_id


def test_d01_requires_prior_reference_percentile_and_sample_floor():
    d = DetectorDefinition(minimum_reference_count=100)
    rows = [classified(0, "25"), classified(1, "5")]
    refs = {
        rows[0].trade.raw_event_hash: SizeReference(
            "GC-RTH", Decimal("20"), Decimal("0.995"), 200, NOW - timedelta(seconds=1)
        ),
        rows[1].trade.raw_event_hash: SizeReference(
            "GC-RTH", Decimal("2"), Decimal("0.999"), 20, NOW - timedelta(seconds=1)
        ),
    }
    found = detect_unusually_large_prints(rows, refs, d)
    assert len(found) == 1
    assert found[0].quantity == Decimal("25")
    assert found[0].side == AggressorSide.BUY


def test_d02_clusters_are_fixed_window_non_overlapping_and_keep_unknown():
    d = DetectorDefinition(
        cluster_window=timedelta(seconds=5),
        cluster_minimum_prints=3,
        cluster_minimum_quantity=Decimal("20"),
    )
    rows = [
        classified(0, "10"),
        classified(1, "8", AggressorSide.BUY),
        classified(2, "5", AggressorSide.UNKNOWN),
        classified(6, "10"),
        classified(7, "10"),
        classified(8, "10"),
    ]
    # Make the last cluster a distinct instrument-independent time group.
    found = detect_large_trade_clusters(
        [
            __import__(
                "researchos.quant_engine.order_flow.detectors", fromlist=["LargePrintCandidate"]
            ).LargePrintCandidate(
                x.trade.raw_event_hash,
                x.trade.instrument_id,
                x.trade.event_time_utc,
                x.trade.quantity,
                x.side,
                x.method,
                "GC-RTH",
                Decimal("0.995"),
                200,
                NOW - timedelta(seconds=1),
                d.definition_id,
            )
            for x in rows
        ],
        d,
    )
    assert len(found) == 2
    assert found[0].total_quantity == Decimal("23")
    assert found[0].unknown_quantity == Decimal("5")
    assert found[0].side == AggressorSide.UNKNOWN
    assert found[1].print_count == 3


def test_d05_keeps_exchange_and_quote_inference_separate_and_fails_low_coverage():
    d = DetectorDefinition(minimum_classified_coverage=Decimal("0.8"))
    f = flow(ex_buy="8", ex_sell="0", quote_buy="0", quote_sell="2", unknown="0")
    ex = classify_aggression_price_response(
        f,
        source=FlowSource.EXCHANGE_FLAG,
        price_progress_ticks=Decimal("1"),
        trailing_volatility_ticks=Decimal("4"),
        volatility_as_of_utc=NOW - timedelta(seconds=1),
        definition=d,
    )
    qi = classify_aggression_price_response(
        f,
        source=FlowSource.QUOTE_INFERRED,
        price_progress_ticks=Decimal("5"),
        trailing_volatility_ticks=Decimal("3"),
        volatility_as_of_utc=NOW - timedelta(seconds=1),
        definition=d,
    )
    assert ex.state == FootprintState.HIGH_AGGRESSION_LOW_PROGRESS
    assert ex.aggressive_buy_quantity == Decimal("8")
    assert qi.state == FootprintState.INSUFFICIENT_DATA
    assert qi.aggressive_sell_quantity == Decimal("2")


def test_d06_requires_repeated_tests_and_directional_aggression():
    d = DetectorDefinition(absorption_minimum_tests=2)
    f = flow(ex_buy="10")
    a = classify_aggression_price_response(
        f,
        source=FlowSource.EXCHANGE_FLAG,
        price_progress_ticks=Decimal("1"),
        trailing_volatility_ticks=Decimal("4"),
        volatility_as_of_utc=NOW - timedelta(seconds=1),
        definition=d,
    )
    b = a.__class__(
        a.instrument_id,
        a.session_id,
        NOW + timedelta(seconds=2),
        NOW + timedelta(seconds=3),
        a.source,
        a.aggressive_buy_quantity,
        a.aggressive_sell_quantity,
        a.classified_coverage,
        a.price_progress_ticks,
        a.trailing_volatility_ticks,
        a.volatility_as_of_utc,
        a.normalized_price_progress,
        a.state,
        a.definition_id,
    )
    assert (
        detect_absorption_candidate(
            [a, b],
            side=AggressorSide.BUY,
            contested_level=Decimal("2400"),
            contested_level_available_at_utc=NOW - timedelta(seconds=1),
            test_count=2,
            definition=d,
        )
        is not None
    )
    assert (
        detect_absorption_candidate(
            [a],
            side=AggressorSide.BUY,
            contested_level=Decimal("2400"),
            contested_level_available_at_utc=NOW - timedelta(seconds=1),
            test_count=1,
            definition=d,
        )
        is None
    )


def test_d08_requires_preexisting_level_trade_through_and_timed_response():
    d = DetectorDefinition(sweep_response_window=timedelta(seconds=5))
    level = ReferenceLevel(
        "prior-swing-low",
        "GCZ6",
        Decimal("2400"),
        "swing_low",
        NOW - timedelta(seconds=10),
        "market_structure_confirmed_swing",
    )
    obs = SweepObservation(
        level, NOW, Decimal("2399"), Decimal("4"), NOW + timedelta(seconds=2), Decimal("2400")
    )
    found = detect_liquidity_sweep_candidate(obs, tick_size=Decimal("0.1"), definition=d)
    assert found is not None
    assert found.direction == "BELOW_REFERENCE"
    assert found.response == "REJECTION"
    future_level = ReferenceLevel(
        "future", "GCZ6", Decimal("2400"), "swing_low", NOW + timedelta(seconds=1), "not_yet_known"
    )
    assert (
        detect_liquidity_sweep_candidate(
            SweepObservation(
                future_level,
                NOW,
                Decimal("2399"),
                Decimal("4"),
                NOW + timedelta(seconds=2),
                Decimal("2400"),
            ),
            tick_size=Decimal("0.1"),
            definition=d,
        )
        is None
    )


def test_d01_rejects_reference_distribution_that_ends_at_or_after_trade():
    d = DetectorDefinition(minimum_reference_count=1)
    item = classified(0, "25")
    ref = SizeReference("GC-RTH", Decimal("20"), Decimal("0.999"), 200, NOW)
    assert detect_unusually_large_prints([item], {item.trade.raw_event_hash: ref}, d) == ()


def test_d05_rejects_volatility_estimate_from_after_the_flow_window():
    import pytest

    d = DetectorDefinition()
    with pytest.raises(ValueError, match="available before"):
        classify_aggression_price_response(
            flow(ex_buy="10"),
            source=FlowSource.EXCHANGE_FLAG,
            price_progress_ticks=Decimal("1"),
            trailing_volatility_ticks=Decimal("4"),
            volatility_as_of_utc=NOW + timedelta(seconds=1),
            definition=d,
        )


def test_d06_rejects_level_that_was_not_known_before_flow_window():
    d = DetectorDefinition(absorption_minimum_tests=2)
    f = flow(ex_buy="10")
    response = classify_aggression_price_response(
        f,
        source=FlowSource.EXCHANGE_FLAG,
        price_progress_ticks=Decimal("1"),
        trailing_volatility_ticks=Decimal("4"),
        volatility_as_of_utc=NOW - timedelta(seconds=1),
        definition=d,
    )
    assert (
        detect_absorption_candidate(
            [response],
            side=AggressorSide.BUY,
            contested_level=Decimal("2400"),
            contested_level_available_at_utc=NOW + timedelta(seconds=1),
            test_count=2,
            definition=d,
        )
        is None
    )
