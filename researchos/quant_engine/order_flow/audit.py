"""Deterministic replay, temporal prefix, and lineage audits.

This module does not connect to feeds. Sequence validation is intentionally
strict and applies only when the caller's registered feed contract guarantees
integer, contiguous per-stream sequence numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Callable, Iterable, Mapping, TypeAlias

from researchos.quant_engine.order_flow.contracts import L2BookEvent, QuoteEvent, TradeEvent
from researchos.quant_engine.order_flow.event_ledger import TradeMutation
from researchos.quant_engine.order_flow.lineage import InputLineage

MarketEvent: TypeAlias = TradeEvent | QuoteEvent | L2BookEvent | TradeMutation


def _utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")


def _canonical_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        _utc(value, "datetime")
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite Decimal cannot be canonicalized")
        return format(value, "f")
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "__type__": value.__class__.__qualname__,
            **{field.name: _canonical_value(getattr(value, field.name)) for field in fields(value)},
        }
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("canonical mapping keys must be strings")
        return {key: _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        raise TypeError("float is not accepted in canonical audit payloads; use Decimal")
    raise TypeError(f"unsupported canonical value: {type(value).__qualname__}")


def canonical_bytes(value: object) -> bytes:
    """Stable UTF-8 JSON encoding; Decimal and timestamps retain exact semantics."""
    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _stream_key(event: MarketEvent) -> tuple[str, str, str, str]:
    return (
        event.source_id,
        event.dataset_id,
        event.instrument_id,
        event.__class__.__qualname__,
    )


@dataclass(frozen=True, slots=True)
class ReplayAudit:
    event_count: int
    stream_count: int
    canonical_events_sha256: str
    replay_sha256: str
    code_revision: str


class SequenceMode(str, Enum):
    CONTIGUOUS = "CONTIGUOUS"
    MONOTONIC = "MONOTONIC"


@dataclass(frozen=True, slots=True)
class SequencePolicy:
    """Explicit source-stream sequence semantics after any vendor adapter."""

    mode: SequenceMode = SequenceMode.CONTIGUOUS
    expected_first_sequence: int | None = 1
    require_event_time_monotonic: bool = True
    require_receive_time_monotonic: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.mode, SequenceMode):
            raise TypeError("mode must be SequenceMode")
        if self.expected_first_sequence is not None and (
            isinstance(self.expected_first_sequence, bool)
            or not isinstance(self.expected_first_sequence, int)
            or self.expected_first_sequence < 0
        ):
            raise ValueError("expected_first_sequence must be a non-negative int or None")
        if not isinstance(self.require_event_time_monotonic, bool) or not isinstance(
            self.require_receive_time_monotonic, bool
        ):
            raise TypeError("sequence monotonicity requirements must be bool")


def build_replay_audit(
    events: Iterable[MarketEvent],
    *,
    replay_config: Mapping[str, object],
    code_revision: str,
    expected_first_sequence: int | None = 1,
    sequence_policies: Mapping[tuple[str, str, str, str], SequencePolicy] | None = None,
    sequence_ordinals: Mapping[str, int] | None = None,
    stream_partitions: Mapping[str, str] | None = None,
) -> ReplayAudit:
    """Audit replay with explicit per-stream sequence and reset policies.

    Integer contiguous sequences retain the legacy default. Vendor string
    sequences require an explicit raw-hash -> integer ordinal adapter.
    Sequence resets are supported only when every event in that stream has an
    explicit partition ID, so each epoch is independently validated.
    """
    if not isinstance(code_revision, str) or not code_revision.strip():
        raise ValueError("code_revision must be non-empty")
    default_policy = SequencePolicy(
        mode=SequenceMode.CONTIGUOUS,
        expected_first_sequence=expected_first_sequence,
    )
    ordinal_map = dict(sequence_ordinals or {})
    partition_map = dict(stream_partitions or {})
    policies = dict(sequence_policies or {})
    if any(
        not isinstance(k, str) or not isinstance(v, int) or isinstance(v, bool)
        for k, v in ordinal_map.items()
    ):
        raise TypeError("sequence_ordinals must map raw event hashes to integer ordinals")
    if any(
        not isinstance(k, str) or not isinstance(v, str) or not v.strip()
        for k, v in partition_map.items()
    ):
        raise TypeError("stream_partitions must map raw event hashes to non-empty partition IDs")

    materialized = tuple(events)
    allowed_types = (TradeEvent, QuoteEvent, L2BookEvent, TradeMutation)
    if any(not isinstance(event, allowed_types) for event in materialized):
        raise TypeError("unsupported market event type")
    event_hashes = {event.raw_event_hash for event in materialized}
    if set(ordinal_map) - event_hashes or set(partition_map) - event_hashes:
        raise ValueError("sequence adapter mappings contain unknown raw event hashes")

    streams: dict[tuple[str, str, str, str], list[MarketEvent]] = {}
    for event in materialized:
        streams.setdefault(_stream_key(event), []).append(event)
    if set(policies) - set(streams):
        raise ValueError("sequence_policies contains an unknown stream key")

    canonical_rows: list[tuple[str, MarketEvent]] = []
    for stream_key in sorted(streams):
        group = streams[stream_key]
        explicitly_partitioned = [event.raw_event_hash in partition_map for event in group]
        if any(explicitly_partitioned) and not all(explicitly_partitioned):
            raise ValueError(f"stream {stream_key} has incomplete reset partition mapping")
        partitioned: dict[str, list[MarketEvent]] = {}
        for event in group:
            partition_id = partition_map.get(event.raw_event_hash, "default")
            partitioned.setdefault(partition_id, []).append(event)
        policy = policies.get(stream_key, default_policy)
        if not isinstance(policy, SequencePolicy):
            raise TypeError(f"invalid sequence policy for stream {stream_key}")

        for partition_id in sorted(partitioned):
            partition_events = partitioned[partition_id]
            ordinals: list[tuple[int, MarketEvent]] = []
            for event in partition_events:
                raw_sequence = event.sequence_number
                if isinstance(raw_sequence, bool):
                    raise ValueError(f"stream {stream_key} contains boolean sequence")
                if isinstance(raw_sequence, int):
                    ordinal = raw_sequence
                    if (
                        event.raw_event_hash in ordinal_map
                        and ordinal_map[event.raw_event_hash] != ordinal
                    ):
                        raise ValueError("integer sequence conflicts with supplied adapter ordinal")
                elif isinstance(raw_sequence, str):
                    if event.raw_event_hash not in ordinal_map:
                        raise ValueError(
                            f"stream {stream_key} requires explicit ordinal adapter for string sequence"
                        )
                    ordinal = ordinal_map[event.raw_event_hash]
                else:
                    raise ValueError(f"stream {stream_key} requires integer sequence number")
                if ordinal < 0:
                    raise ValueError(f"stream {stream_key} contains negative sequence ordinal")
                ordinals.append((ordinal, event))

            ordinals.sort(key=lambda pair: pair[0])
            values = [ordinal for ordinal, _ in ordinals]
            if len(set(values)) != len(values):
                raise ValueError(
                    f"stream {stream_key} partition {partition_id} has duplicate sequence ordinals"
                )
            if (
                policy.expected_first_sequence is not None
                and values[0] != policy.expected_first_sequence
            ):
                raise ValueError(
                    f"stream {stream_key} partition {partition_id} does not start at expected sequence"
                )
            for previous, current in zip(values, values[1:]):
                if policy.mode == SequenceMode.CONTIGUOUS and current != previous + 1:
                    raise ValueError(
                        f"stream {stream_key} partition {partition_id} contains sequence gap"
                    )
                if policy.mode == SequenceMode.MONOTONIC and current <= previous:
                    raise ValueError(
                        f"stream {stream_key} partition {partition_id} is not strictly increasing"
                    )
            hashes = [event.raw_event_hash for _, event in ordinals]
            if len(set(hashes)) != len(hashes):
                raise ValueError(
                    f"stream {stream_key} partition {partition_id} has duplicate raw event hashes"
                )
            for (_, previous), (_, current) in zip(ordinals, ordinals[1:]):
                if (
                    policy.require_event_time_monotonic
                    and current.event_time_utc < previous.event_time_utc
                ):
                    raise ValueError(f"stream {stream_key} event time regresses by sequence")
                if (
                    policy.require_receive_time_monotonic
                    and current.receive_time_utc < previous.receive_time_utc
                ):
                    raise ValueError(f"stream {stream_key} receive time regresses by sequence")
            canonical_rows.extend((partition_id, event) for _, event in ordinals)

    events_payload = canonical_bytes(
        tuple(
            {"partition_id": partition_id, "event": event} for partition_id, event in canonical_rows
        )
    )
    events_hash = _sha256(events_payload)
    policy_payload = {
        "|".join(key): {
            "mode": policy.mode.value,
            "expected_first_sequence": policy.expected_first_sequence,
            "require_event_time_monotonic": policy.require_event_time_monotonic,
            "require_receive_time_monotonic": policy.require_receive_time_monotonic,
        }
        for key, policy in policies.items()
    }
    replay_payload = canonical_bytes(
        {
            "canonical_events_sha256": events_hash,
            "replay_config": replay_config,
            "code_revision": code_revision,
            "default_expected_first_sequence": expected_first_sequence,
            "sequence_policies": policy_payload,
            "sequence_ordinals": ordinal_map,
            "stream_partitions": partition_map,
        }
    )
    return ReplayAudit(
        event_count=len(canonical_rows),
        stream_count=sum(
            len({partition_map.get(event.raw_event_hash, "default") for event in group})
            for group in streams.values()
        ),
        canonical_events_sha256=events_hash,
        replay_sha256=_sha256(replay_payload),
        code_revision=code_revision,
    )


@dataclass(frozen=True, slots=True)
class PrefixInvariantResult:
    cutoff_utc: datetime
    prefix_event_count: int
    full_event_count: int
    historical_output_count: int
    prefix_output_sha256: str
    full_replay_prefix_sha256: str
    passed: bool


def audit_prefix_invariance(
    events: Iterable[MarketEvent],
    *,
    cutoff_utc: datetime,
    replay: Callable[[tuple[MarketEvent, ...]], Iterable[object]],
    output_available_at: Callable[[object], datetime],
) -> PrefixInvariantResult:
    """Compare outputs available by T from prefix-only and full replay.

    Input prefix is selected by receive_time_utc <= T, not event time: an event
    is not available to a live process until it has been received.
    """
    _utc(cutoff_utc, "cutoff_utc")
    materialized = tuple(events)
    prefix = tuple(event for event in materialized if event.receive_time_utc <= cutoff_utc)

    def historical_digest(outputs: Iterable[object]) -> tuple[int, str]:
        selected = []
        for output in outputs:
            available = output_available_at(output)
            _utc(available, "output_available_at")
            if available <= cutoff_utc:
                selected.append(output)
        payload = canonical_bytes(tuple(selected))
        return len(selected), _sha256(payload)

    prefix_count, prefix_hash = historical_digest(replay(prefix))
    full_count, full_hash = historical_digest(replay(materialized))
    return PrefixInvariantResult(
        cutoff_utc=cutoff_utc,
        prefix_event_count=len(prefix),
        full_event_count=len(materialized),
        historical_output_count=prefix_count,
        prefix_output_sha256=prefix_hash,
        full_replay_prefix_sha256=full_hash,
        passed=prefix_count == full_count and prefix_hash == full_hash,
    )


@dataclass(frozen=True, slots=True)
class LineageRecord:
    output_sha256: str
    input_event_hashes: tuple[str, ...]
    definition_id: str
    code_revision: str
    latest_input_event_time_utc: datetime
    latest_input_available_at_utc: datetime
    output_available_at_utc: datetime

    def __post_init__(self) -> None:
        for name in ("output_sha256", "definition_id"):
            value = getattr(self, name)
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"{name} must be lowercase SHA-256")
        if not self.code_revision.strip():
            raise ValueError("code_revision must be non-empty")
        if not self.input_event_hashes:
            raise ValueError("input_event_hashes must be non-empty")
        for digest in self.input_event_hashes:
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise ValueError("input_event_hashes must contain lowercase SHA-256 values")
        if tuple(sorted(set(self.input_event_hashes))) != self.input_event_hashes:
            raise ValueError("input_event_hashes must be unique and sorted")
        for name in (
            "latest_input_event_time_utc",
            "latest_input_available_at_utc",
            "output_available_at_utc",
        ):
            _utc(getattr(self, name), name)
        if self.latest_input_available_at_utc < self.latest_input_event_time_utc:
            raise ValueError("input cannot be available before its event time")
        if self.output_available_at_utc < self.latest_input_available_at_utc:
            raise ValueError("output cannot be available before its latest input")

    @property
    def lineage_sha256(self) -> str:
        return _sha256(canonical_bytes(self))


def build_lineage_record_from_input_lineage(
    output: object,
    *,
    input_lineage: InputLineage,
    definition_id: str,
    code_revision: str,
    output_available_at_utc: datetime,
) -> LineageRecord:
    """Create a lineage record only when every required dependency is resolved."""
    if not isinstance(input_lineage, InputLineage):
        raise TypeError("input_lineage must be InputLineage")
    if not input_lineage.complete:
        raise ValueError(
            "cannot certify detector output with incomplete input lineage: "
            + ", ".join(input_lineage.missing_inputs)
        )
    if (
        input_lineage.latest_input_event_time_utc is None
        or input_lineage.latest_input_available_at_utc is None
    ):
        raise ValueError("complete input lineage must include causal clocks")
    return build_lineage_record(
        output,
        input_event_hashes=input_lineage.input_event_hashes,
        definition_id=definition_id,
        code_revision=code_revision,
        latest_input_event_time_utc=input_lineage.latest_input_event_time_utc,
        latest_input_available_at_utc=input_lineage.latest_input_available_at_utc,
        output_available_at_utc=output_available_at_utc,
    )


@dataclass(frozen=True, slots=True)
class DetectorPipelineAudit:
    """Combined raw replay, prefix-invariance, and complete-output-lineage result."""

    replay_audit: ReplayAudit
    prefix_invariance: PrefixInvariantResult
    lineage_records: tuple[LineageRecord, ...]

    @property
    def passed(self) -> bool:
        return self.prefix_invariance.passed and all(
            record.output_available_at_utc >= record.latest_input_available_at_utc
            for record in self.lineage_records
        )


def audit_detector_pipeline(
    events: Iterable[MarketEvent],
    *,
    cutoff_utc: datetime,
    replay: Callable[[tuple[MarketEvent, ...]], Iterable[object]],
    output_available_at: Callable[[object], datetime],
    definition_id: Callable[[object], str],
    replay_config: Mapping[str, object],
    code_revision: str,
    expected_first_sequence: int | None = 1,
    sequence_policies: Mapping[tuple[str, str, str, str], SequencePolicy] | None = None,
    sequence_ordinals: Mapping[str, int] | None = None,
    stream_partitions: Mapping[str, str] | None = None,
) -> DetectorPipelineAudit:
    """Run one fail-closed audit across raw replay, historical prefix, and lineage.

    Both prefix-only and full replay outputs must carry complete event-derived
    InputLineage. Outputs without a definition ID, causal clocks, or complete
    raw input hashes are rejected rather than treated as certified.
    """
    _utc(cutoff_utc, "cutoff_utc")
    materialized = tuple(events)
    replay_audit = build_replay_audit(
        materialized,
        replay_config=replay_config,
        code_revision=code_revision,
        expected_first_sequence=expected_first_sequence,
        sequence_policies=sequence_policies,
        sequence_ordinals=sequence_ordinals,
        stream_partitions=stream_partitions,
    )
    prefix_events = tuple(event for event in materialized if event.receive_time_utc <= cutoff_utc)
    prefix_outputs = tuple(replay(prefix_events))
    full_outputs = tuple(replay(materialized))

    def validate_outputs(
        outputs: tuple[object, ...],
    ) -> tuple[tuple[object, datetime], tuple[LineageRecord, ...]]:
        validated: list[tuple[object, datetime]] = []
        records: list[LineageRecord] = []
        for output in outputs:
            available_at = output_available_at(output)
            _utc(available_at, "output_available_at")
            lineage = getattr(output, "input_lineage", None)
            if not isinstance(lineage, InputLineage):
                raise ValueError("detector output is missing InputLineage")
            record = build_lineage_record_from_input_lineage(
                output,
                input_lineage=lineage,
                definition_id=definition_id(output),
                code_revision=code_revision,
                output_available_at_utc=available_at,
            )
            validated.append((output, available_at))
            records.append(record)
        return tuple(validated), tuple(records)

    prefix_validated, _ = validate_outputs(prefix_outputs)
    full_validated, lineage_records = validate_outputs(full_outputs)

    def historical_digest(outputs: tuple[tuple[object, datetime], ...]) -> tuple[int, str]:
        selected = tuple(output for output, available_at in outputs if available_at <= cutoff_utc)
        return len(selected), _sha256(canonical_bytes(selected))

    prefix_count, prefix_hash = historical_digest(prefix_validated)
    full_count, full_hash = historical_digest(full_validated)
    prefix_result = PrefixInvariantResult(
        cutoff_utc=cutoff_utc,
        prefix_event_count=len(prefix_events),
        full_event_count=len(materialized),
        historical_output_count=prefix_count,
        prefix_output_sha256=prefix_hash,
        full_replay_prefix_sha256=full_hash,
        passed=prefix_count == full_count and prefix_hash == full_hash,
    )
    return DetectorPipelineAudit(replay_audit, prefix_result, lineage_records)


def build_lineage_record_from_events(
    output: object,
    *,
    input_events: Iterable[MarketEvent],
    definition_id: str,
    code_revision: str,
    output_available_at_utc: datetime,
) -> LineageRecord:
    """Derive lineage hashes and input clocks from the actual immutable events."""
    input_lineage = InputLineage.from_events(input_events)
    if input_lineage is None:
        raise ValueError("input_events must be non-empty")
    return build_lineage_record_from_input_lineage(
        output,
        input_lineage=input_lineage,
        definition_id=definition_id,
        code_revision=code_revision,
        output_available_at_utc=output_available_at_utc,
    )


def build_lineage_record(
    output: object,
    *,
    input_event_hashes: Iterable[str],
    definition_id: str,
    code_revision: str,
    latest_input_event_time_utc: datetime,
    latest_input_available_at_utc: datetime,
    output_available_at_utc: datetime,
) -> LineageRecord:
    """Build an auditable envelope; input hashes/times must come from the caller."""
    return LineageRecord(
        output_sha256=_sha256(canonical_bytes(output)),
        input_event_hashes=tuple(sorted(set(input_event_hashes))),
        definition_id=definition_id,
        code_revision=code_revision,
        latest_input_event_time_utc=latest_input_event_time_utc,
        latest_input_available_at_utc=latest_input_available_at_utc,
        output_available_at_utc=output_available_at_utc,
    )
