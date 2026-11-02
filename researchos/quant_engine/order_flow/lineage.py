"""Event-derived input lineage for deterministic detector outputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from researchos.quant_engine.order_flow.contracts import L2BookEvent, QuoteEvent, TradeEvent
from researchos.quant_engine.order_flow.event_ledger import TradeMutation


LineageEvent = TradeEvent | QuoteEvent | L2BookEvent | TradeMutation


def _utc(value: datetime | None, name: str) -> None:
    if value is None or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")


@dataclass(frozen=True, slots=True)
class InputLineage:
    """Raw input identity plus causal clocks; incomplete dependencies stay explicit."""

    input_event_hashes: tuple[str, ...]
    latest_input_event_time_utc: datetime | None
    latest_input_available_at_utc: datetime | None
    complete: bool
    missing_inputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if tuple(sorted(set(self.input_event_hashes))) != self.input_event_hashes:
            raise ValueError("input_event_hashes must be unique and sorted")
        for digest in self.input_event_hashes:
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("input_event_hashes must contain lowercase SHA-256")
        if not isinstance(self.complete, bool):
            raise TypeError("complete must be bool")
        if any(not item or item.strip() != item for item in self.missing_inputs):
            raise ValueError("missing_inputs must contain non-empty trimmed labels")
        if self.latest_input_event_time_utc is None:
            if self.latest_input_available_at_utc is not None:
                raise ValueError("availability clock requires an event-time clock")
        else:
            _utc(self.latest_input_event_time_utc, "latest_input_event_time_utc")
            _utc(self.latest_input_available_at_utc, "latest_input_available_at_utc")
            if self.latest_input_available_at_utc < self.latest_input_event_time_utc:
                raise ValueError("input availability cannot precede latest input event time")
        if self.complete and (
            not self.input_event_hashes
            or self.latest_input_event_time_utc is None
            or self.latest_input_available_at_utc is None
            or self.missing_inputs
        ):
            raise ValueError("complete lineage requires hashes, clocks, and no missing inputs")

    @classmethod
    def from_events(
        cls,
        events: Iterable[LineageEvent],
        *,
        unresolved_hashes: Iterable[str] = (),
        missing_inputs: Iterable[str] = (),
    ) -> InputLineage | None:
        rows = tuple(events)
        unresolved = tuple(unresolved_hashes)
        missing = tuple(missing_inputs)
        if not rows and not unresolved and not missing:
            return None
        by_hash: dict[str, LineageEvent] = {}
        for event in rows:
            if not isinstance(event, (TradeEvent, QuoteEvent, L2BookEvent, TradeMutation)):
                raise TypeError("unsupported lineage event")
            prior = by_hash.get(event.raw_event_hash)
            if prior is not None and prior != event:
                raise ValueError("same raw hash has conflicting lineage event payload")
            by_hash[event.raw_event_hash] = event
        hashes = set(by_hash) | set(unresolved)
        ordered_hashes = tuple(sorted(hashes))
        if not by_hash:
            return cls(
                ordered_hashes,
                None,
                None,
                False,
                tuple(sorted(set(missing) | {"unresolved_event_clocks"})),
            )
        event_time = max(event.event_time_utc for event in by_hash.values())
        available_at = max(event.receive_time_utc for event in by_hash.values())
        missing_set = set(missing)
        if unresolved:
            missing_set.add("unresolved_event_clocks")
        return cls(
            ordered_hashes,
            event_time,
            available_at,
            not missing_set,
            tuple(sorted(missing_set)),
        )


def combine_input_lineage(
    lineages: Iterable[InputLineage | None],
    *,
    missing_inputs: Iterable[str] = (),
) -> InputLineage | None:
    """Union lineage from all required detector inputs without hiding gaps."""
    rows = tuple(lineages)
    missing = set(missing_inputs)
    if any(item is None for item in rows):
        missing.add("missing_input_lineage")
    known = tuple(item for item in rows if item is not None)
    if not known and not missing:
        return None
    hashes = tuple(sorted({digest for item in known for digest in item.input_event_hashes}))
    times = [item.latest_input_event_time_utc for item in known if item.latest_input_event_time_utc]
    availability = [
        item.latest_input_available_at_utc for item in known if item.latest_input_available_at_utc
    ]
    for item in known:
        missing.update(item.missing_inputs)
        if not item.complete:
            missing.add("incomplete_upstream_lineage")
    if not times:
        return InputLineage(
            hashes, None, None, False, tuple(sorted(missing | {"missing_event_clocks"}))
        )
    return InputLineage(
        hashes,
        max(times),
        max(availability),
        not missing and bool(hashes),
        tuple(sorted(missing)),
    )
