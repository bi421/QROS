"""Correction-aware, deterministic trade event ledger.

Corrections and cancels are immutable mutations; a cancel is not a zero-size trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import hashlib
from typing import Iterable

from researchos.quant_engine.order_flow.contracts import TradeEvent


class TradeMutationAction(str, Enum):
    NEW = "NEW"
    CORRECT = "CORRECT"
    CANCEL = "CANCEL"


def _require_utc(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")


@dataclass(frozen=True, slots=True)
class TradeMutation:
    source_id: str
    dataset_id: str
    instrument_id: str
    trade_id: str
    trade_scope_id: str
    revision: int
    action: TradeMutationAction
    event_time_utc: datetime
    receive_time_utc: datetime
    raw_event_hash: str
    sequence_number: int | str
    replacement_trade: TradeEvent | None = None
    supersedes_raw_event_hash: str | None = None

    def __post_init__(self) -> None:
        for name in ("source_id", "dataset_id", "instrument_id", "trade_id", "trade_scope_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value.strip() != value:
                raise ValueError(f"{name} must be a non-empty trimmed string")
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 1
        ):
            raise ValueError("revision must be a positive integer")
        if not isinstance(self.action, TradeMutationAction):
            raise TypeError("action must be TradeMutationAction")
        _require_utc(self.event_time_utc, "event_time_utc")
        _require_utc(self.receive_time_utc, "receive_time_utc")
        if self.receive_time_utc < self.event_time_utc:
            raise ValueError("receive_time_utc cannot precede event_time_utc")
        if isinstance(self.sequence_number, bool) or not isinstance(
            self.sequence_number, (int, str)
        ):
            raise TypeError("sequence_number must be int or str")
        if isinstance(self.sequence_number, str) and (
            not self.sequence_number or self.sequence_number.strip() != self.sequence_number
        ):
            raise ValueError("string sequence_number must be non-empty and trimmed")
        if len(self.raw_event_hash) != 64 or any(
            c not in "0123456789abcdef" for c in self.raw_event_hash
        ):
            raise ValueError("raw_event_hash must be lowercase SHA-256")
        if self.action == TradeMutationAction.NEW:
            if (
                self.revision != 1
                or self.supersedes_raw_event_hash is not None
                or self.replacement_trade is None
            ):
                raise ValueError(
                    "NEW requires revision 1, replacement trade, and no superseded hash"
                )
        elif self.action == TradeMutationAction.CORRECT:
            if (
                self.revision < 2
                or self.supersedes_raw_event_hash is None
                or self.replacement_trade is None
            ):
                raise ValueError(
                    "CORRECT requires revision >= 2, superseded hash, and replacement trade"
                )
        else:
            if (
                self.revision < 2
                or self.supersedes_raw_event_hash is None
                or self.replacement_trade is not None
            ):
                raise ValueError(
                    "CANCEL requires revision >= 2, superseded hash, and no replacement trade"
                )
        if self.supersedes_raw_event_hash is not None and (
            len(self.supersedes_raw_event_hash) != 64
            or any(c not in "0123456789abcdef" for c in self.supersedes_raw_event_hash)
        ):
            raise ValueError("supersedes_raw_event_hash must be lowercase SHA-256")
        if self.replacement_trade is not None:
            trade = self.replacement_trade
            if (
                trade.source_id != self.source_id
                or trade.dataset_id != self.dataset_id
                or trade.instrument_id != self.instrument_id
                or trade.trade_id != self.trade_id
            ):
                raise ValueError("replacement trade identity must match mutation identity")
            if trade.receive_time_utc != self.receive_time_utc:
                raise ValueError(
                    "replacement trade receive time must equal mutation availability time"
                )


@dataclass(frozen=True, slots=True)
class TradeLedgerSnapshot:
    active_trades: tuple[TradeEvent, ...]
    applied_mutation_hashes: tuple[str, ...]
    duplicate_mutation_count: int
    ledger_sha256: str
    applied_mutations: tuple[TradeMutation, ...] = ()
    active_trade_mutation_histories: tuple[tuple[TradeMutation, ...], ...] = ()

    def __post_init__(self) -> None:
        if len(self.active_trades) != len(self.active_trade_mutation_histories):
            raise ValueError("each active trade must have one mutation history")
        if (
            tuple(item.raw_event_hash for item in self.applied_mutations)
            != self.applied_mutation_hashes
        ):
            raise ValueError("applied mutation events and hashes must align")
        for trade, history in zip(self.active_trades, self.active_trade_mutation_histories):
            if not history or history[-1].replacement_trade != trade:
                raise ValueError("active trade mutation history must end at the active trade")
            if any(item.action == TradeMutationAction.CANCEL for item in history):
                raise ValueError("active trade mutation history cannot contain a cancel")

    def mutations_for_active_trade(self, trade: TradeEvent) -> tuple[TradeMutation, ...]:
        """Return the complete NEW/CORRECT chain for this exact active trade."""
        for active, history in zip(self.active_trades, self.active_trade_mutation_histories):
            if active == trade:
                return history
        raise KeyError("trade is not active in this ledger snapshot")

    def lineage_events_for_active_trade(
        self, trade: TradeEvent
    ) -> tuple[TradeMutation | TradeEvent, ...]:
        """Return every mutation and every historical payload for InputLineage."""
        history = self.mutations_for_active_trade(trade)
        payloads = tuple(
            item.replacement_trade for item in history if item.replacement_trade is not None
        )
        return (*history, *payloads)


def replay_trade_mutations(mutations: Iterable[TradeMutation]) -> TradeLedgerSnapshot:
    """Apply mutations in supplied causal order; exact duplicate hashes are idempotent."""
    from researchos.quant_engine.order_flow.audit import canonical_bytes

    active: dict[tuple[str, str, str, str, str], TradeEvent] = {}
    active_histories: dict[tuple[str, str, str, str, str], list[TradeMutation]] = {}
    revisions: dict[tuple[str, str, str, str, str], int] = {}
    last_received: dict[tuple[str, str, str, str, str], datetime] = {}
    seen: dict[str, bytes] = {}
    ordered_unique: list[TradeMutation] = []
    duplicate_count = 0

    for mutation in mutations:
        if not isinstance(mutation, TradeMutation):
            raise TypeError("all ledger inputs must be TradeMutation")
        payload = canonical_bytes(mutation)
        prior_payload = seen.get(mutation.raw_event_hash)
        if prior_payload is not None:
            if prior_payload != payload:
                raise ValueError("same mutation hash has conflicting payload")
            duplicate_count += 1
            continue
        seen[mutation.raw_event_hash] = payload
        key = (
            mutation.source_id,
            mutation.dataset_id,
            mutation.instrument_id,
            mutation.trade_scope_id,
            mutation.trade_id,
        )
        expected_revision = revisions.get(key, 0) + 1
        if mutation.revision != expected_revision:
            raise ValueError(
                f"trade {mutation.trade_id} expected revision {expected_revision}, got {mutation.revision}"
            )
        previous_receive = last_received.get(key)
        if previous_receive is not None and mutation.receive_time_utc < previous_receive:
            raise ValueError("trade mutation receive time regresses")
        current = active.get(key)
        if mutation.action == TradeMutationAction.NEW:
            if current is not None:
                raise ValueError("NEW cannot replace an already active trade")
        else:
            if current is None:
                raise ValueError("CORRECT/CANCEL requires an active trade")
            if mutation.supersedes_raw_event_hash != current.raw_event_hash:
                raise ValueError("mutation does not supersede the current active trade version")
        if mutation.action == TradeMutationAction.CANCEL:
            del active[key]
            del active_histories[key]
        else:
            assert mutation.replacement_trade is not None
            active[key] = mutation.replacement_trade
            if mutation.action == TradeMutationAction.NEW:
                active_histories[key] = [mutation]
            else:
                active_histories[key].append(mutation)
        revisions[key] = mutation.revision
        last_received[key] = mutation.receive_time_utc
        ordered_unique.append(mutation)

    active_trades = tuple(
        sorted(
            active.values(),
            key=lambda trade: (
                trade.source_id,
                trade.dataset_id,
                trade.instrument_id,
                trade.trade_id or "",
                trade.raw_event_hash,
            ),
        )
    )
    hashes = tuple(m.raw_event_hash for m in ordered_unique)
    active_keys = sorted(
        active,
        key=lambda key: (
            active[key].source_id,
            active[key].dataset_id,
            active[key].instrument_id,
            active[key].trade_id or "",
            active[key].raw_event_hash,
        ),
    )
    active_histories = tuple(tuple(active_histories[key]) for key in active_keys)
    digest = hashlib.sha256(
        canonical_bytes({"mutations": tuple(ordered_unique), "active_trades": active_trades})
    ).hexdigest()
    return TradeLedgerSnapshot(
        active_trades,
        hashes,
        duplicate_count,
        digest,
        tuple(ordered_unique),
        active_histories,
    )
