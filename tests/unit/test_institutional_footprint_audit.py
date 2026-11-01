from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from researchos.quant_engine.order_flow.audit import (
    audit_prefix_invariance,
    build_lineage_record,
    canonical_bytes,
    build_replay_audit,
)
from researchos.quant_engine.order_flow.contracts import (
    AggressorSide,
    QuoteEvent,
    TradeEvent,
)
from researchos.quant_engine.order_flow.features import classify_trade

NOW = datetime(2026, 11, 2, 4, 0, tzinfo=timezone.utc)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
REVISION = "d" * 40


def trade(
    seq: int,
    *,
    event_seconds: int | None = None,
    receive_seconds: int | None = None,
    digest: str | None = None,
):
    event_at = NOW + timedelta(seconds=seq if event_seconds is None else event_seconds)
    receive_at = NOW + timedelta(
        seconds=seq if receive_seconds is None else receive_seconds, milliseconds=1
    )
    return TradeEvent(
        source_id="synthetic-trades",
        dataset_id="synthetic-v1",
        instrument_id="GCZ6",
        event_time_utc=event_at,
        receive_time_utc=receive_at,
        price=Decimal("2400.0"),
        quantity=Decimal(seq),
        raw_event_hash=digest or {1: HASH_A, 2: HASH_B, 3: HASH_C}[seq],
        sequence_number=seq,
    )


def test_replay_hash_is_invariant_to_input_permutation_with_valid_sequence():
    events = (trade(1), trade(2), trade(3))
    forward = build_replay_audit(
        events, replay_config={"window_seconds": 5}, code_revision=REVISION
    )
    shuffled = build_replay_audit(
        (events[2], events[0], events[1]),
        replay_config={"window_seconds": 5},
        code_revision=REVISION,
    )
    assert forward == shuffled
    assert forward.event_count == 3
    assert forward.stream_count == 1


def test_replay_hash_changes_when_config_or_code_revision_changes():
    events = (trade(1), trade(2))
    base = build_replay_audit(events, replay_config={"threshold": "0.8"}, code_revision=REVISION)
    changed_config = build_replay_audit(
        events, replay_config={"threshold": "0.9"}, code_revision=REVISION
    )
    changed_code = build_replay_audit(
        events, replay_config={"threshold": "0.8"}, code_revision="e" * 40
    )
    assert len({base.replay_sha256, changed_config.replay_sha256, changed_code.replay_sha256}) == 3


def test_replay_rejects_missing_or_non_integer_sequence():
    with pytest.raises(ValueError, match="integer sequence"):
        build_replay_audit(
            (
                trade(1, digest=HASH_A).__class__(
                    source_id="synthetic-trades",
                    dataset_id="synthetic-v1",
                    instrument_id="GCZ6",
                    event_time_utc=NOW,
                    receive_time_utc=NOW + timedelta(milliseconds=1),
                    price=Decimal("2400"),
                    quantity=Decimal("1"),
                    raw_event_hash=HASH_A,
                ),
            ),
            replay_config={},
            code_revision=REVISION,
        )


def test_replay_rejects_duplicate_sequence_and_duplicate_raw_hash():
    first = trade(1)
    duplicate_sequence = trade(1, digest=HASH_B)
    with pytest.raises(ValueError, match="duplicate sequence"):
        build_replay_audit((first, duplicate_sequence), replay_config={}, code_revision=REVISION)
    duplicate_hash = trade(2, digest=HASH_A)
    with pytest.raises(ValueError, match="duplicate raw event hashes"):
        build_replay_audit((first, duplicate_hash), replay_config={}, code_revision=REVISION)


def test_replay_rejects_sequence_gap_and_wrong_first_sequence():
    with pytest.raises(ValueError, match="sequence gap"):
        build_replay_audit((trade(1), trade(3)), replay_config={}, code_revision=REVISION)
    with pytest.raises(ValueError, match="does not start"):
        build_replay_audit((trade(2), trade(3)), replay_config={}, code_revision=REVISION)


def test_replay_rejects_receive_or_event_time_regression_by_sequence():
    receive_regression = (
        trade(1, event_seconds=1, receive_seconds=5),
        trade(2, event_seconds=2, receive_seconds=3),
    )
    with pytest.raises(ValueError, match="receive time regresses"):
        build_replay_audit(receive_regression, replay_config={}, code_revision=REVISION)
    event_regression = (
        trade(1, event_seconds=5, receive_seconds=6),
        trade(2, event_seconds=2, receive_seconds=7),
    )
    with pytest.raises(ValueError, match="event time regresses"):
        build_replay_audit(event_regression, replay_config={}, code_revision=REVISION)


@dataclass(frozen=True)
class ReplayOutput:
    source_hash: str
    available_at_utc: datetime
    value: Decimal


def test_prefix_invariance_passes_when_future_quotes_cannot_reclassify_old_trade():
    item = trade(1)
    late_quote = QuoteEvent(
        source_id="synthetic-quotes",
        dataset_id="synthetic-v1",
        instrument_id="GCZ6",
        event_time_utc=item.event_time_utc - timedelta(milliseconds=1),
        receive_time_utc=item.receive_time_utc + timedelta(seconds=1),
        bid_price=Decimal("2399.9"),
        ask_price=Decimal("2400.0"),
        raw_event_hash=HASH_B,
        sequence_number=1,
    )

    def replay(events):
        quotes = tuple(event for event in events if isinstance(event, QuoteEvent))
        outputs = []
        for event in events:
            if isinstance(event, TradeEvent):
                result = classify_trade(event, quotes, max_quote_age=timedelta(seconds=2))
                outputs.append(
                    ReplayOutput(
                        event.raw_event_hash,
                        event.receive_time_utc,
                        Decimal("1") if result.side == AggressorSide.BUY else Decimal("0"),
                    )
                )
        return tuple(outputs)

    result = audit_prefix_invariance(
        (item, late_quote),
        cutoff_utc=item.receive_time_utc,
        replay=replay,
        output_available_at=lambda output: output.available_at_utc,
    )
    assert result.passed
    assert result.prefix_event_count == 1
    assert result.full_event_count == 2
    assert result.historical_output_count == 1


def test_prefix_invariance_detects_future_leakage_in_historical_output():
    first, future = trade(1), trade(2)

    def leaky_replay(events):
        has_future = any(event.raw_event_hash == HASH_B for event in events)
        return (ReplayOutput(HASH_A, first.receive_time_utc, Decimal("2" if has_future else "1")),)

    result = audit_prefix_invariance(
        (first, future),
        cutoff_utc=first.receive_time_utc,
        replay=leaky_replay,
        output_available_at=lambda output: output.available_at_utc,
    )
    assert not result.passed
    assert result.prefix_output_sha256 != result.full_replay_prefix_sha256


def test_lineage_record_hashes_output_and_rejects_lookahead():
    output = {"event": "BUY_ABSORPTION_CANDIDATE", "quantity": Decimal("12.5")}
    record = build_lineage_record(
        output,
        input_event_hashes=(HASH_B, HASH_A),
        definition_id=HASH_C,
        code_revision=REVISION,
        latest_input_event_time_utc=NOW,
        latest_input_available_at_utc=NOW + timedelta(milliseconds=2),
        output_available_at_utc=NOW + timedelta(milliseconds=3),
    )
    assert record.input_event_hashes == (HASH_A, HASH_B)
    assert len(record.output_sha256) == 64
    assert len(record.lineage_sha256) == 64
    with pytest.raises(ValueError, match="before its latest input"):
        build_lineage_record(
            output,
            input_event_hashes=(HASH_A,),
            definition_id=HASH_C,
            code_revision=REVISION,
            latest_input_event_time_utc=NOW,
            latest_input_available_at_utc=NOW + timedelta(seconds=2),
            output_available_at_utc=NOW + timedelta(seconds=1),
        )


def test_lineage_record_requires_real_hashes_and_unique_sorted_inputs():
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        build_lineage_record(
            {"x": 1},
            input_event_hashes=(HASH_A,),
            definition_id="bad",
            code_revision=REVISION,
            latest_input_event_time_utc=NOW,
            latest_input_available_at_utc=NOW,
            output_available_at_utc=NOW,
        )


def test_canonical_json_is_mapping_order_invariant_and_rejects_float():
    assert canonical_bytes({"b": Decimal("1.25"), "a": 2}) == canonical_bytes(
        {"a": 2, "b": Decimal("1.25")}
    )
    with pytest.raises(TypeError, match="float is not accepted"):
        canonical_bytes({"unsafe": 0.1})
