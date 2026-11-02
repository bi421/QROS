from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from researchos.quant_engine.order_flow.contracts import AggressorMethod, AggressorSide, TradeEvent
from researchos.quant_engine.order_flow.features import FlowWindow, TradeClassification
from researchos.quant_engine.order_flow.lineage import InputLineage
from researchos.quant_engine.order_flow.event_ledger import TradeMutation, TradeMutationAction
from researchos.quant_engine.order_flow.detectors import (
    DetectorDefinition,
    FlowSource,
    FlowResponse,
    FootprintState,
    LargePrintCandidate,
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
            "GCZ6",
            "RTH",
            "GC-RTH",
            Decimal("20"),
            Decimal("0.995"),
            200,
            NOW - timedelta(seconds=1),
        ),
        rows[1].trade.raw_event_hash: SizeReference(
            "GCZ6", "RTH", "GC-RTH", Decimal("2"), Decimal("0.999"), 20, NOW - timedelta(seconds=1)
        ),
    }
    found = detect_unusually_large_prints(
        rows,
        refs,
        d,
        session_ids={item.trade.raw_event_hash: "RTH" for item in rows},
    )
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
    # A separate later cluster remains within the same session/cohort.
    found = detect_large_trade_clusters(
        [
            LargePrintCandidate(
                x.trade.raw_event_hash,
                x.trade.source_id,
                x.trade.dataset_id,
                x.trade.instrument_id,
                "RTH",
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
        level,
        "GCZ6",
        HASH,
        NOW,
        Decimal("2399"),
        Decimal("4"),
        NOW + timedelta(seconds=2),
        Decimal("2400.1"),
    )
    found = detect_liquidity_sweep_candidate(obs, tick_size=Decimal("0.1"), definition=d)
    assert found is not None
    assert found.direction == "BELOW_REFERENCE"
    assert found.response == "RECLAIMED_REFERENCE_BY_WINDOW_END"
    future_level = ReferenceLevel(
        "future", "GCZ6", Decimal("2400"), "swing_low", NOW + timedelta(seconds=1), "not_yet_known"
    )
    assert (
        detect_liquidity_sweep_candidate(
            SweepObservation(
                future_level,
                "GCZ6",
                HASH,
                NOW,
                Decimal("2399"),
                Decimal("4"),
                NOW + timedelta(seconds=2),
                Decimal("2400.1"),
            ),
            tick_size=Decimal("0.1"),
            definition=d,
        )
        is None
    )


def test_d01_rejects_reference_distribution_that_ends_at_or_after_trade():
    d = DetectorDefinition(minimum_reference_count=1)
    item = classified(0, "25")
    ref = SizeReference("GCZ6", "RTH", "GC-RTH", Decimal("20"), Decimal("0.999"), 200, NOW)
    assert (
        detect_unusually_large_prints(
            [item],
            {item.trade.raw_event_hash: ref},
            d,
            session_ids={item.trade.raw_event_hash: "RTH"},
        )
        == ()
    )


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


def test_d01_rejects_reference_from_another_instrument():
    item = classified(0, "25")
    wrong_instrument = SizeReference(
        "MGCZ6", "RTH", "MGC-RTH", Decimal("20"), Decimal("0.999"), 200, NOW - timedelta(seconds=1)
    )
    assert (
        detect_unusually_large_prints(
            [item],
            {item.trade.raw_event_hash: wrong_instrument},
            DetectorDefinition(minimum_reference_count=1),
            session_ids={item.trade.raw_event_hash: "RTH"},
        )
        == ()
    )


def test_d02_never_clusters_across_session_boundaries():
    d = DetectorDefinition(cluster_minimum_prints=3, cluster_minimum_quantity=Decimal("1"))
    rows = []
    for n, session in ((0, "RTH"), (1, "RTH"), (2, "ETH")):
        item = classified(n, "10")
        rows.append(
            LargePrintCandidate(
                item.trade.raw_event_hash,
                item.trade.source_id,
                item.trade.dataset_id,
                item.trade.instrument_id,
                session,
                item.trade.event_time_utc,
                item.trade.quantity,
                item.side,
                item.method,
                f"GC-{session}",
                Decimal("0.995"),
                200,
                NOW - timedelta(seconds=1),
                d.definition_id,
            )
        )
    assert detect_large_trade_clusters(rows, d) == ()


def test_d08_exact_reference_touch_is_not_mislabelled_acceptance():
    level = ReferenceLevel(
        "prior-swing-low",
        "GCZ6",
        Decimal("2400"),
        "swing_low",
        NOW - timedelta(seconds=2),
        "confirmed_swing",
    )
    observation = SweepObservation(
        level,
        "GCZ6",
        HASH,
        NOW,
        Decimal("2399"),
        Decimal("2"),
        NOW + timedelta(seconds=1),
        Decimal("2400"),
    )
    result = detect_liquidity_sweep_candidate(
        observation, tick_size=Decimal("0.1"), definition=DetectorDefinition()
    )
    assert result is not None
    assert result.response == "AT_REFERENCE_AT_WINDOW_END"


def test_d08_rejects_mismatched_instrument_and_off_tick_prices():
    level = ReferenceLevel(
        "prior-swing-low",
        "GCZ6",
        Decimal("2400"),
        "swing_low",
        NOW - timedelta(seconds=2),
        "confirmed_swing",
    )
    with pytest.raises(ValueError, match="instrument does not match"):
        SweepObservation(
            level,
            "MGCZ6",
            HASH,
            NOW,
            Decimal("2399"),
            Decimal("2"),
            NOW + timedelta(seconds=1),
            Decimal("2400"),
        )
    valid_identity = SweepObservation(
        level,
        "GCZ6",
        HASH,
        NOW,
        Decimal("2399.05"),
        Decimal("2"),
        NOW + timedelta(seconds=1),
        Decimal("2400"),
    )
    with pytest.raises(ValueError, match="align to tick_size"):
        detect_liquidity_sweep_candidate(
            valid_identity, tick_size=Decimal("0.1"), definition=DetectorDefinition()
        )


def test_d06_does_not_combine_exchange_and_quote_inferred_evidence():
    from dataclasses import replace

    d = DetectorDefinition(absorption_minimum_tests=2)
    f = flow(ex_buy="10")
    exchange = classify_aggression_price_response(
        f,
        source=FlowSource.EXCHANGE_FLAG,
        price_progress_ticks=Decimal("1"),
        trailing_volatility_ticks=Decimal("4"),
        volatility_as_of_utc=NOW - timedelta(seconds=1),
        definition=d,
    )
    quote_inferred = replace(exchange, source=FlowSource.QUOTE_INFERRED)
    assert (
        detect_absorption_candidate(
            [exchange, quote_inferred],
            side=AggressorSide.BUY,
            contested_level=Decimal("2400"),
            contested_level_available_at_utc=NOW - timedelta(seconds=1),
            test_count=2,
            definition=d,
        )
        is None
    )


def test_d08_distinguishes_still_beyond_reference_from_reclaim():
    level = ReferenceLevel(
        "prior-swing-low",
        "GCZ6",
        Decimal("2400"),
        "swing_low",
        NOW - timedelta(seconds=2),
        "confirmed_swing",
    )
    observation = SweepObservation(
        level,
        "GCZ6",
        HASH,
        NOW,
        Decimal("2399"),
        Decimal("2"),
        NOW + timedelta(seconds=1),
        Decimal("2398.9"),
    )
    result = detect_liquidity_sweep_candidate(
        observation, tick_size=Decimal("0.1"), definition=DetectorDefinition()
    )
    assert result is not None
    assert result.response == "REMAINS_BEYOND_REFERENCE_AT_WINDOW_END"


def test_d01_rejects_reference_from_another_session_and_requires_session_mapping():
    item = classified(0, "25")
    reference = SizeReference(
        "GCZ6",
        "ETH",
        "GC-ETH",
        Decimal("20"),
        Decimal("0.999"),
        200,
        NOW - timedelta(seconds=1),
    )
    refs = {item.trade.raw_event_hash: reference}
    with pytest.raises(ValueError, match="missing session mapping"):
        detect_unusually_large_prints(
            [item], refs, DetectorDefinition(minimum_reference_count=1), session_ids={}
        )
    assert (
        detect_unusually_large_prints(
            [item],
            refs,
            DetectorDefinition(minimum_reference_count=1),
            session_ids={item.trade.raw_event_hash: "RTH"},
        )
        == ()
    )


def test_d01_lineage_includes_scored_trade_and_reference_sample_events():
    definition = DetectorDefinition(minimum_reference_count=100)
    sample = classified(0, "30")
    scored = classified(2, "25")
    reference = SizeReference(
        "GCZ6",
        "RTH",
        "GC-RTH",
        Decimal("20"),
        Decimal("0.995"),
        200,
        NOW + timedelta(seconds=1),
        InputLineage.from_events((sample.trade,)),
    )
    candidates = detect_unusually_large_prints(
        (scored,),
        {scored.trade.raw_event_hash: reference},
        definition,
        session_ids={scored.trade.raw_event_hash: "RTH"},
    )
    assert len(candidates) == 1
    assert candidates[0].input_lineage is not None
    assert candidates[0].input_lineage.complete
    assert set(candidates[0].input_lineage.input_event_hashes) == {
        sample.trade.raw_event_hash,
        scored.trade.raw_event_hash,
    }


def test_d01_rejects_reference_lineage_received_after_scored_trade():
    definition = DetectorDefinition(minimum_reference_count=100)
    from dataclasses import replace

    sample = replace(
        classified(1, "30").trade,
        receive_time_utc=NOW + timedelta(seconds=4),
    )
    scored = classified(2, "25")
    reference = SizeReference(
        "GCZ6",
        "RTH",
        "GC-RTH",
        Decimal("20"),
        Decimal("0.995"),
        200,
        NOW + timedelta(seconds=1),
        InputLineage.from_events((sample,)),
    )
    candidates = detect_unusually_large_prints(
        (scored,),
        {scored.trade.raw_event_hash: reference},
        definition,
        session_ids={scored.trade.raw_event_hash: "RTH"},
    )
    assert candidates == ()


def test_d05_lineage_requires_flow_price_and_volatility_raw_events():
    from dataclasses import replace

    definition = DetectorDefinition()
    flow_event = classified(3).trade
    price_event = classified(4).trade
    volatility_event = classified(1).trade
    flow_window = replace(
        flow(),
        start_utc=NOW + timedelta(seconds=3),
        end_utc=NOW + timedelta(seconds=4),
        input_lineage=InputLineage.from_events((flow_event,)),
    )
    response = classify_aggression_price_response(
        flow_window,
        source=FlowSource.EXCHANGE_FLAG,
        price_progress_ticks=Decimal("0"),
        trailing_volatility_ticks=Decimal("4"),
        volatility_as_of_utc=NOW + timedelta(seconds=2),
        definition=definition,
        price_input_events=(price_event,),
        volatility_input_events=(volatility_event,),
    )
    assert response.input_lineage is not None
    assert response.input_lineage.complete
    assert len(response.input_lineage.input_event_hashes) == 3


def test_d06_lineage_includes_supporting_flow_and_contested_level_events():
    definition = DetectorDefinition()
    first_event = classified(3).trade
    second_event = classified(5).trade
    level_event = classified(1).trade
    first = FlowResponse(
        "GCZ6",
        "RTH",
        NOW + timedelta(seconds=3),
        NOW + timedelta(seconds=4),
        FlowSource.EXCHANGE_FLAG,
        Decimal("10"),
        Decimal("0"),
        Decimal("1"),
        Decimal("0"),
        Decimal("4"),
        NOW + timedelta(seconds=2),
        Decimal("0"),
        FootprintState.HIGH_AGGRESSION_LOW_PROGRESS,
        definition.definition_id,
        InputLineage.from_events((first_event,)),
    )
    second = FlowResponse(
        "GCZ6",
        "RTH",
        NOW + timedelta(seconds=5),
        NOW + timedelta(seconds=6),
        FlowSource.EXCHANGE_FLAG,
        Decimal("12"),
        Decimal("0"),
        Decimal("1"),
        Decimal("0"),
        Decimal("4"),
        NOW + timedelta(seconds=4),
        Decimal("0"),
        FootprintState.HIGH_AGGRESSION_LOW_PROGRESS,
        definition.definition_id,
        InputLineage.from_events((second_event,)),
    )
    candidate = detect_absorption_candidate(
        (first, second),
        side=AggressorSide.BUY,
        contested_level=Decimal("2400.0"),
        contested_level_available_at_utc=NOW + timedelta(seconds=2),
        test_count=2,
        definition=definition,
        contested_level_input_events=(level_event,),
    )
    assert candidate is not None
    assert candidate.input_lineage is not None
    assert candidate.input_lineage.complete
    assert len(candidate.input_lineage.input_event_hashes) == 3


def test_d08_lineage_requires_reference_trade_through_and_response_events():
    definition = DetectorDefinition()
    level_event = classified(0).trade
    trade_through = classified(2).trade
    response_event = classified(3).trade
    reference = ReferenceLevel(
        "prior-high",
        "GCZ6",
        Decimal("2399.9"),
        "PRIOR_HIGH",
        NOW + timedelta(seconds=1),
        "SYNTHETIC",
        InputLineage.from_events((level_event,)),
    )
    observation = SweepObservation(
        reference,
        "GCZ6",
        trade_through.raw_event_hash,
        trade_through.event_time_utc,
        trade_through.price,
        trade_through.quantity,
        NOW + timedelta(seconds=3),
        response_event.price,
        trade_through,
        response_event,
    )
    candidate = detect_liquidity_sweep_candidate(
        observation, tick_size=Decimal("0.1"), definition=definition
    )
    assert candidate is not None
    assert candidate.input_lineage is not None
    assert candidate.input_lineage.complete
    assert len(candidate.input_lineage.input_event_hashes) == 3


def test_d06_rejects_cross_instrument_contested_level_lineage():
    definition = DetectorDefinition()
    first_event = classified(3).trade
    second_event = classified(5).trade
    wrong_instrument_level_event = replace(classified(1).trade, instrument_id="MGCZ6")
    first = FlowResponse(
        "GCZ6",
        "RTH",
        NOW + timedelta(seconds=3),
        NOW + timedelta(seconds=4),
        FlowSource.EXCHANGE_FLAG,
        Decimal("10"),
        Decimal("0"),
        Decimal("1"),
        Decimal("0"),
        Decimal("4"),
        NOW + timedelta(seconds=2),
        Decimal("0"),
        FootprintState.HIGH_AGGRESSION_LOW_PROGRESS,
        definition.definition_id,
        InputLineage.from_events((first_event,)),
    )
    second = FlowResponse(
        "GCZ6",
        "RTH",
        NOW + timedelta(seconds=5),
        NOW + timedelta(seconds=6),
        FlowSource.EXCHANGE_FLAG,
        Decimal("12"),
        Decimal("0"),
        Decimal("1"),
        Decimal("0"),
        Decimal("4"),
        NOW + timedelta(seconds=4),
        Decimal("0"),
        FootprintState.HIGH_AGGRESSION_LOW_PROGRESS,
        definition.definition_id,
        InputLineage.from_events((second_event,)),
    )
    with pytest.raises(ValueError, match="match the flow instrument"):
        detect_absorption_candidate(
            (first, second),
            side=AggressorSide.BUY,
            contested_level=Decimal("2400.0"),
            contested_level_available_at_utc=NOW + timedelta(seconds=2),
            test_count=2,
            definition=definition,
            contested_level_input_events=(wrong_instrument_level_event,),
        )


def test_d08_rejects_response_event_that_precedes_trade_through():
    level_event = classified(0).trade
    trade_through = classified(2).trade
    earlier_response = classified(1).trade
    reference = ReferenceLevel(
        "prior-high",
        "GCZ6",
        Decimal("2399.9"),
        "PRIOR_HIGH",
        NOW + timedelta(seconds=1),
        "SYNTHETIC",
        InputLineage.from_events((level_event,)),
    )
    with pytest.raises(ValueError, match="does not match sweep response window"):
        SweepObservation(
            reference,
            "GCZ6",
            trade_through.raw_event_hash,
            trade_through.event_time_utc,
            trade_through.price,
            trade_through.quantity,
            NOW + timedelta(seconds=3),
            earlier_response.price,
            trade_through,
            earlier_response,
        )


def test_d08_lineage_preserves_trade_through_correction_history():
    from dataclasses import replace

    original = replace(classified(1).trade, trade_id="T-1")
    corrected = replace(classified(2).trade, trade_id="T-1")
    new = TradeMutation(
        original.source_id,
        original.dataset_id,
        original.instrument_id,
        "T-1",
        "RTH-2026-11-02",
        1,
        TradeMutationAction.NEW,
        original.event_time_utc,
        original.receive_time_utc,
        "f" * 64,
        1,
        original,
    )
    correction = TradeMutation(
        corrected.source_id,
        corrected.dataset_id,
        corrected.instrument_id,
        "T-1",
        "RTH-2026-11-02",
        2,
        TradeMutationAction.CORRECT,
        corrected.event_time_utc,
        corrected.receive_time_utc,
        "e" * 64,
        2,
        corrected,
        original.raw_event_hash,
    )
    level_event = classified(0).trade
    response_event = classified(3).trade
    reference = ReferenceLevel(
        "prior-high",
        "GCZ6",
        Decimal("2399.9"),
        "PRIOR_HIGH",
        NOW + timedelta(seconds=1),
        "SYNTHETIC",
        InputLineage.from_events((level_event,)),
    )
    observation = SweepObservation(
        reference,
        "GCZ6",
        corrected.raw_event_hash,
        corrected.event_time_utc,
        corrected.price,
        corrected.quantity,
        NOW + timedelta(seconds=3),
        response_event.price,
        corrected,
        response_event,
        (new, correction),
    )
    candidate = detect_liquidity_sweep_candidate(
        observation, tick_size=Decimal("0.1"), definition=DetectorDefinition()
    )
    assert candidate is not None
    assert candidate.input_lineage is not None
    assert candidate.input_lineage.complete
    assert set(candidate.input_lineage.input_event_hashes) >= {
        original.raw_event_hash,
        corrected.raw_event_hash,
        new.raw_event_hash,
        correction.raw_event_hash,
        level_event.raw_event_hash,
        response_event.raw_event_hash,
    }
