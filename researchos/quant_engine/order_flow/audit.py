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

MarketEvent: TypeAlias = TradeEvent | QuoteEvent | L2BookEvent


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


def build_replay_audit(
    events: Iterable[MarketEvent],
    *,
    replay_config: Mapping[str, object],
    code_revision: str,
    expected_first_sequence: int | None = 1,
) -> ReplayAudit:
    """Canonicalize valid per-stream sequence order and hash inputs/config/revision.

    Missing, duplicate, non-integer, gapped, event-time-regressing, or
    receive-time-regressing sequences fail closed. This must only be used with
    a feed whose manifest explicitly documents contiguous integer sequences.
    """
    if not code_revision.strip():
        raise ValueError("code_revision must be non-empty")
    if expected_first_sequence is not None and (
        isinstance(expected_first_sequence, bool)
        or not isinstance(expected_first_sequence, int)
        or expected_first_sequence < 0
    ):
        raise TypeError("expected_first_sequence must be a non-negative int or None")

    groups: dict[tuple[str, str, str, str], list[MarketEvent]] = {}
    for event in events:
        if not isinstance(event, (TradeEvent, QuoteEvent, L2BookEvent)):
            raise TypeError("unsupported market event type")
        groups.setdefault(_stream_key(event), []).append(event)

    canonical_events: list[MarketEvent] = []
    for key in sorted(groups):
        group = groups[key]
        if any(
            isinstance(event.sequence_number, bool) or not isinstance(event.sequence_number, int)
            for event in group
        ):
            raise ValueError(f"stream {key} requires integer sequence numbers")
        ordered = sorted(group, key=lambda event: event.sequence_number)
        sequences = [event.sequence_number for event in ordered]
        if any(sequence < 0 for sequence in sequences):
            raise ValueError(f"stream {key} contains a negative sequence number")
        if len(set(sequences)) != len(sequences):
            raise ValueError(f"stream {key} contains duplicate sequence numbers")
        if expected_first_sequence is not None and sequences[0] != expected_first_sequence:
            raise ValueError(f"stream {key} does not start at expected sequence")
        if any(current != previous + 1 for previous, current in zip(sequences, sequences[1:])):
            raise ValueError(f"stream {key} contains a sequence gap")
        hashes = [event.raw_event_hash for event in ordered]
        if len(set(hashes)) != len(hashes):
            raise ValueError(f"stream {key} contains duplicate raw event hashes")
        for previous, current in zip(ordered, ordered[1:]):
            if current.event_time_utc < previous.event_time_utc:
                raise ValueError(f"stream {key} event time regresses by sequence")
            if current.receive_time_utc < previous.receive_time_utc:
                raise ValueError(f"stream {key} receive time regresses by sequence")
        canonical_events.extend(ordered)

    events_payload = canonical_bytes(tuple(canonical_events))
    events_hash = _sha256(events_payload)
    replay_payload = canonical_bytes(
        {
            "canonical_events_sha256": events_hash,
            "replay_config": replay_config,
            "code_revision": code_revision,
        }
    )
    return ReplayAudit(
        event_count=len(canonical_events),
        stream_count=len(groups),
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
