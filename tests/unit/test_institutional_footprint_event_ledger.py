from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from researchos.quant_engine.order_flow.audit import (
    SequenceMode,
    SequencePolicy,
    build_replay_audit,
)
from researchos.quant_engine.order_flow.contracts import TradeEvent
from researchos.quant_engine.order_flow.features import (
    aggregate_trade_flow,
    classify_trade_from_ledger,
)
from researchos.quant_engine.order_flow.event_ledger import (
    TradeMutation,
    TradeMutationAction,
    replay_trade_mutations,
)

NOW = datetime(2026, 11, 2, 4, 0, tzinfo=timezone.utc)
REVISION = "d" * 40


def trade(seq, *, digest, price="2400", quantity="2", trade_id="T-1", sequence=None):
    return TradeEvent(
        source_id="vendor-x",
        dataset_id="gc-v1",
        instrument_id="GCZ6",
        event_time_utc=NOW + timedelta(seconds=seq),
        receive_time_utc=NOW + timedelta(seconds=seq, milliseconds=1),
        price=Decimal(price),
        quantity=Decimal(quantity),
        raw_event_hash=digest,
        sequence_number=seq if sequence is None else sequence,
        trade_id=trade_id,
    )


def mutation(seq, action, *, digest, replacement=None, supersedes=None, revision=None):
    return TradeMutation(
        source_id="vendor-x",
        dataset_id="gc-v1",
        instrument_id="GCZ6",
        trade_id="T-1",
        trade_scope_id="session-2026-11-02",
        revision=seq if revision is None else revision,
        action=action,
        event_time_utc=NOW + timedelta(seconds=seq),
        receive_time_utc=NOW + timedelta(seconds=seq, milliseconds=1),
        raw_event_hash=digest,
        sequence_number=seq,
        replacement_trade=replacement,
        supersedes_raw_event_hash=supersedes,
    )


def test_trade_mutation_correction_replaces_prior_version():
    original = trade(1, digest="a" * 64, price="2400", quantity="2")
    corrected = trade(2, digest="b" * 64, price="2401", quantity="3")
    new = mutation(1, TradeMutationAction.NEW, digest="1" * 64, replacement=original)
    correction = mutation(
        2,
        TradeMutationAction.CORRECT,
        digest="2" * 64,
        replacement=corrected,
        supersedes=original.raw_event_hash,
    )
    result = replay_trade_mutations((new, correction))
    assert result.active_trades == (corrected,)
    assert result.applied_mutation_hashes == ("1" * 64, "2" * 64)
    assert result.applied_mutations == (new, correction)
    assert result.mutations_for_active_trade(corrected) == (new, correction)
    assert result.lineage_events_for_active_trade(corrected) == (
        new,
        correction,
        original,
        corrected,
    )
    assert len(result.ledger_sha256) == 64


def test_trade_mutation_cancel_removes_trade_from_active_snapshot():
    original = trade(1, digest="a" * 64)
    new = mutation(1, TradeMutationAction.NEW, digest="1" * 64, replacement=original)
    cancel = mutation(
        2,
        TradeMutationAction.CANCEL,
        digest="2" * 64,
        supersedes=original.raw_event_hash,
    )
    result = replay_trade_mutations((new, cancel))
    assert result.active_trades == ()
    assert result.applied_mutations == (new, cancel)
    assert result.active_trade_mutation_histories == ()
    assert len(result.applied_mutation_hashes) == 2


def test_exact_duplicate_mutation_is_idempotent():
    original = trade(1, digest="a" * 64)
    new = mutation(1, TradeMutationAction.NEW, digest="1" * 64, replacement=original)
    result = replay_trade_mutations((new, new))
    assert result.active_trades == (original,)
    assert result.duplicate_mutation_count == 1
    assert result.applied_mutation_hashes == ("1" * 64,)


def test_mutation_requires_current_superseded_hash_and_next_revision():
    original = trade(1, digest="a" * 64)
    new = mutation(1, TradeMutationAction.NEW, digest="1" * 64, replacement=original)
    wrong = mutation(
        2,
        TradeMutationAction.CANCEL,
        digest="2" * 64,
        supersedes="f" * 64,
    )
    with pytest.raises(ValueError, match="current active"):
        replay_trade_mutations((new, wrong))
    skipped = mutation(
        3,
        TradeMutationAction.CANCEL,
        digest="3" * 64,
        supersedes=original.raw_event_hash,
        revision=3,
    )
    with pytest.raises(ValueError, match="expected revision"):
        replay_trade_mutations((new, skipped))


def test_mutation_hash_collision_with_different_payload_fails_closed():
    first_trade = trade(1, digest="a" * 64, quantity="2")
    second_trade = trade(1, digest="a" * 64, quantity="5")
    first = mutation(1, TradeMutationAction.NEW, digest="1" * 64, replacement=first_trade)
    conflicting = mutation(1, TradeMutationAction.NEW, digest="1" * 64, replacement=second_trade)
    with pytest.raises(ValueError, match="conflicting payload"):
        replay_trade_mutations((first, conflicting))


def test_string_vendor_sequences_require_explicit_ordinal_adapter():
    events = (
        trade(1, digest="a" * 64, sequence="seq-A"),
        trade(2, digest="b" * 64, sequence="seq-B"),
    )
    with pytest.raises(ValueError, match="ordinal adapter"):
        build_replay_audit(events, replay_config={}, code_revision=REVISION)
    audit = build_replay_audit(
        events,
        replay_config={"vendor_sequence": "opaque-string-adapted"},
        code_revision=REVISION,
        sequence_ordinals={"a" * 64: 1, "b" * 64: 2},
    )
    assert audit.event_count == 2


def test_vendor_monotonic_policy_can_allow_documented_gaps():
    events = (
        trade(1, digest="a" * 64, sequence="A-10"),
        trade(2, digest="b" * 64, sequence="A-12"),
    )
    key = ("vendor-x", "gc-v1", "GCZ6", "TradeEvent")
    policy = SequencePolicy(
        mode=SequenceMode.MONOTONIC,
        expected_first_sequence=10,
    )
    audit = build_replay_audit(
        events,
        replay_config={},
        code_revision=REVISION,
        sequence_policies={key: policy},
        sequence_ordinals={"a" * 64: 10, "b" * 64: 12},
    )
    assert audit.event_count == 2
    contiguous_policy = SequencePolicy(
        mode=SequenceMode.CONTIGUOUS,
        expected_first_sequence=10,
    )
    with pytest.raises(ValueError, match="sequence gap"):
        build_replay_audit(
            events,
            replay_config={},
            code_revision=REVISION,
            sequence_policies={key: contiguous_policy},
            sequence_ordinals={"a" * 64: 10, "b" * 64: 12},
        )


def test_sequence_reset_requires_complete_explicit_partitioning():
    events = (
        trade(1, digest="a" * 64),
        trade(2, digest="b" * 64),
        trade(3, digest="c" * 64, sequence=1),
        trade(4, digest="e" * 64, sequence=2),
    )
    with pytest.raises(ValueError, match="duplicate sequence"):
        build_replay_audit(events, replay_config={}, code_revision=REVISION)
    audit = build_replay_audit(
        events,
        replay_config={"sequence_reset": "new_epoch"},
        code_revision=REVISION,
        stream_partitions={
            "a" * 64: "epoch-1",
            "b" * 64: "epoch-1",
            "c" * 64: "epoch-2",
            "e" * 64: "epoch-2",
        },
    )
    assert audit.event_count == 4
    assert audit.stream_count == 2


def test_partial_reset_partition_mapping_is_rejected():
    events = (trade(1, digest="a" * 64), trade(2, digest="b" * 64))
    with pytest.raises(ValueError, match="incomplete reset partition"):
        build_replay_audit(
            events,
            replay_config={},
            code_revision=REVISION,
            stream_partitions={"a" * 64: "epoch-1"},
        )


def test_correction_events_are_included_in_deterministic_replay_audit():
    original = trade(1, digest="a" * 64)
    corrected = trade(2, digest="b" * 64, price="2401")
    new = mutation(1, TradeMutationAction.NEW, digest="1" * 64, replacement=original)
    correction = mutation(
        2,
        TradeMutationAction.CORRECT,
        digest="2" * 64,
        replacement=corrected,
        supersedes=original.raw_event_hash,
    )
    audit = build_replay_audit(
        (new, correction),
        replay_config={"correction_policy": "revision-chain-v1"},
        code_revision=REVISION,
    )
    assert audit.event_count == 2
    assert audit.stream_count == 1


def test_sequence_policy_rejects_invalid_flags_and_unknown_stream_keys():
    with pytest.raises(TypeError, match="must be bool"):
        SequencePolicy(require_event_time_monotonic="yes")
    with pytest.raises(ValueError, match="unknown stream key"):
        build_replay_audit(
            (trade(1, digest="a" * 64),),
            replay_config={},
            code_revision=REVISION,
            sequence_policies={("wrong-source", "gc-v1", "GCZ6", "TradeEvent"): SequencePolicy()},
        )


def test_trade_id_can_be_reused_in_a_distinct_explicit_scope():
    first_trade = trade(1, digest="a" * 64, trade_id="REUSED")
    second_trade = trade(2, digest="b" * 64, trade_id="REUSED")
    first = TradeMutation(
        source_id="vendor-x",
        dataset_id="gc-v1",
        instrument_id="GCZ6",
        trade_id="REUSED",
        trade_scope_id="session-A",
        revision=1,
        action=TradeMutationAction.NEW,
        event_time_utc=NOW + timedelta(seconds=1),
        receive_time_utc=NOW + timedelta(seconds=1, milliseconds=1),
        raw_event_hash="1" * 64,
        sequence_number=1,
        replacement_trade=first_trade,
    )
    second = TradeMutation(
        source_id="vendor-x",
        dataset_id="gc-v1",
        instrument_id="GCZ6",
        trade_id="REUSED",
        trade_scope_id="session-B",
        revision=1,
        action=TradeMutationAction.NEW,
        event_time_utc=NOW + timedelta(seconds=2),
        receive_time_utc=NOW + timedelta(seconds=2, milliseconds=1),
        raw_event_hash="2" * 64,
        sequence_number=2,
        replacement_trade=second_trade,
    )
    result = replay_trade_mutations((first, second))
    assert len(result.active_trades) == 2


def test_corrected_trade_availability_must_match_mutation_receive_time():
    original = trade(1, digest="a" * 64)
    late_corrected = trade(2, digest="b" * 64)
    with pytest.raises(ValueError, match="equal mutation availability"):
        TradeMutation(
            source_id="vendor-x",
            dataset_id="gc-v1",
            instrument_id="GCZ6",
            trade_id="T-1",
            trade_scope_id="session-2026-11-02",
            revision=2,
            action=TradeMutationAction.CORRECT,
            event_time_utc=NOW + timedelta(seconds=2),
            receive_time_utc=NOW + timedelta(seconds=3),
            raw_event_hash="2" * 64,
            sequence_number=2,
            replacement_trade=late_corrected,
            supersedes_raw_event_hash=original.raw_event_hash,
        )


def test_corrected_trade_lineage_survives_classification_and_flow_aggregation():
    original = trade(1, digest="a" * 64, price="2400", quantity="2")
    corrected = trade(2, digest="b" * 64, price="2401", quantity="3")
    new = mutation(1, TradeMutationAction.NEW, digest="1" * 64, replacement=original)
    correction = mutation(
        2,
        TradeMutationAction.CORRECT,
        digest="2" * 64,
        replacement=corrected,
        supersedes=original.raw_event_hash,
    )
    snapshot = replay_trade_mutations((new, correction))
    classification = classify_trade_from_ledger(
        corrected, (), ledger_snapshot=snapshot, max_quote_age=timedelta(seconds=1)
    )
    window = aggregate_trade_flow(
        (classification,),
        instrument_id="GCZ6",
        session_id="RTH",
        start_utc=NOW,
        end_utc=NOW + timedelta(seconds=10),
    )
    assert window.input_lineage is not None
    assert window.input_lineage.complete
    assert window.input_lineage.input_event_hashes == tuple(
        sorted(
            (
                original.raw_event_hash,
                corrected.raw_event_hash,
                new.raw_event_hash,
                correction.raw_event_hash,
            )
        )
    )


def test_ledger_backed_classification_rejects_non_active_trade():
    original = trade(1, digest="a" * 64)
    new = mutation(1, TradeMutationAction.NEW, digest="1" * 64, replacement=original)
    snapshot = replay_trade_mutations((new,))
    different = trade(2, digest="b" * 64)
    with pytest.raises(KeyError, match="not active"):
        classify_trade_from_ledger(
            different, (), ledger_snapshot=snapshot, max_quote_age=timedelta(seconds=1)
        )


def test_cancel_mutations_remain_in_empty_flow_window_lineage():
    original = trade(1, digest="a" * 64)
    new = mutation(1, TradeMutationAction.NEW, digest="1" * 64, replacement=original)
    cancel = mutation(
        2,
        TradeMutationAction.CANCEL,
        digest="2" * 64,
        supersedes=original.raw_event_hash,
    )
    snapshot = replay_trade_mutations((new, cancel))
    window = aggregate_trade_flow(
        (),
        instrument_id="GCZ6",
        session_id="RTH",
        start_utc=NOW,
        end_utc=NOW + timedelta(seconds=10),
        additional_lineage_events=snapshot.applied_mutations,
    )
    assert window.trade_count == 0
    assert window.total_quantity == Decimal("0")
    assert window.input_lineage is not None
    assert window.input_lineage.complete
    assert window.input_lineage.input_event_hashes == tuple(
        sorted((new.raw_event_hash, cancel.raw_event_hash))
    )


def test_flow_rejects_additional_lineage_from_another_instrument():
    other = trade(1, digest="a" * 64)
    other = TradeEvent(
        other.source_id,
        other.dataset_id,
        "MGCZ6",
        other.event_time_utc,
        other.receive_time_utc,
        other.price,
        other.quantity,
        other.raw_event_hash,
        other.aggressor_side,
        other.aggressor_method,
        other.sequence_number,
        other.trade_id,
    )
    with pytest.raises(ValueError, match="match the flow instrument"):
        aggregate_trade_flow(
            (),
            instrument_id="GCZ6",
            session_id="RTH",
            start_utc=NOW,
            end_utc=NOW + timedelta(seconds=10),
            additional_lineage_events=(other,),
        )
