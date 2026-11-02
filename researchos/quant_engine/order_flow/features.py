"""Deterministic trade/quote feature calculations for synthetic research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable

from researchos.quant_engine.order_flow.contracts import (
    AggressorMethod,
    AggressorSide,
    InstrumentMetadata,
    QuoteCondition,
    QuoteEvent,
    TradeEvent,
)
from researchos.quant_engine.order_flow.lineage import InputLineage, LineageEvent
from researchos.quant_engine.order_flow.event_ledger import (
    TradeLedgerSnapshot,
    TradeMutation,
    replay_trade_mutations,
)


@dataclass(frozen=True, slots=True)
class TradeClassification:
    trade: TradeEvent
    side: AggressorSide
    method: AggressorMethod
    quote_hash: str | None
    reason: str
    supporting_quote_events: tuple[QuoteEvent, ...] = ()
    supporting_mutation_events: tuple[TradeMutation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.trade, TradeEvent):
            raise TypeError("trade must be TradeEvent")
        if not isinstance(self.side, AggressorSide):
            raise TypeError("side must be AggressorSide")
        if not isinstance(self.method, AggressorMethod):
            raise TypeError("method must be AggressorMethod")
        if not self.reason:
            raise ValueError("reason must be non-empty")
        if not isinstance(self.supporting_quote_events, tuple) or any(
            not isinstance(quote, QuoteEvent) for quote in self.supporting_quote_events
        ):
            raise TypeError("supporting_quote_events must be a tuple of QuoteEvent")
        if (
            self.quote_hash is not None
            and self.supporting_quote_events
            and self.quote_hash
            not in {quote.raw_event_hash for quote in self.supporting_quote_events}
        ):
            raise ValueError("quote_hash must identify a supporting quote event")
        if not isinstance(self.supporting_mutation_events, tuple) or any(
            not isinstance(item, TradeMutation) for item in self.supporting_mutation_events
        ):
            raise TypeError("supporting_mutation_events must be a tuple of TradeMutation")
        if self.supporting_mutation_events:
            snapshot = replay_trade_mutations(self.supporting_mutation_events)
            if snapshot.active_trades != (self.trade,):
                raise ValueError("supporting mutations must resolve to this exact active trade")
        if self.method == AggressorMethod.UNKNOWN and self.side != AggressorSide.UNKNOWN:
            raise ValueError("UNKNOWN method requires UNKNOWN side")
        if self.method != AggressorMethod.UNKNOWN and self.side == AggressorSide.UNKNOWN:
            raise ValueError("classified method requires BUY or SELL side")


@dataclass(frozen=True, slots=True)
class FlowWindow:
    instrument_id: str
    session_id: str
    start_utc: datetime
    end_utc: datetime
    trade_count: int
    classified_trade_count: int
    unknown_trade_count: int
    total_quantity: Decimal
    buy_quantity: Decimal
    sell_quantity: Decimal
    unknown_quantity: Decimal
    exchange_flag_buy_quantity: Decimal
    exchange_flag_sell_quantity: Decimal
    quote_inferred_buy_quantity: Decimal
    quote_inferred_sell_quantity: Decimal
    exchange_flag_delta: Decimal
    quote_inferred_delta: Decimal
    delta: Decimal
    classified_coverage: Decimal
    input_lineage: InputLineage | None = None


@dataclass(frozen=True, slots=True)
class CvdPoint:
    instrument_id: str
    session_id: str
    start_utc: datetime
    end_utc: datetime
    delta: Decimal
    cvd: Decimal


def classify_trade(
    trade: TradeEvent,
    quotes: Iterable[QuoteEvent],
    *,
    max_quote_age: timedelta,
    supporting_mutations: Iterable[TradeMutation] = (),
) -> TradeClassification:
    """Use exchange side when present; otherwise infer only from a causal valid quote.

    A quote must have an earlier event timestamp and must already have been
    received by the time the trade was received. Equal event timestamps are
    treated as ambiguous because cross-feed sequence ordering is not assumed.
    """
    mutation_events = tuple(supporting_mutations)
    if mutation_events:
        snapshot = replay_trade_mutations(mutation_events)
        if snapshot.active_trades != (trade,):
            raise ValueError("supporting mutations must resolve to this exact active trade")
    if max_quote_age <= timedelta(0):
        raise ValueError("max_quote_age must be positive")

    if trade.aggressor_method == AggressorMethod.EXCHANGE_FLAG:
        return TradeClassification(
            trade,
            trade.aggressor_side,
            AggressorMethod.EXCHANGE_FLAG,
            None,
            "EXCHANGE_FLAG_PRESERVED",
            (),
            mutation_events,
        )
    if trade.aggressor_method == AggressorMethod.QUOTE_INFERRED:
        return TradeClassification(
            trade,
            trade.aggressor_side,
            AggressorMethod.QUOTE_INFERRED,
            None,
            "PRECLASSIFIED_QUOTE_INFERENCE_PRESERVED",
            (),
            mutation_events,
        )

    eligible = [
        quote
        for quote in quotes
        if quote.instrument_id == trade.instrument_id
        and quote.event_time_utc < trade.event_time_utc
        and quote.receive_time_utc <= trade.receive_time_utc
    ]
    if not eligible:
        return TradeClassification(
            trade,
            AggressorSide.UNKNOWN,
            AggressorMethod.UNKNOWN,
            None,
            "NO_CAUSAL_PRIOR_QUOTE",
            (),
            mutation_events,
        )

    latest_time = max(quote.event_time_utc for quote in eligible)
    latest = [quote for quote in eligible if quote.event_time_utc == latest_time]
    if len(latest) != 1:
        return TradeClassification(
            trade,
            AggressorSide.UNKNOWN,
            AggressorMethod.UNKNOWN,
            None,
            "AMBIGUOUS_QUOTE_TIMESTAMP",
            tuple(latest),
            mutation_events,
        )

    quote = latest[0]
    if trade.event_time_utc - quote.event_time_utc > max_quote_age:
        return TradeClassification(
            trade,
            AggressorSide.UNKNOWN,
            AggressorMethod.UNKNOWN,
            quote.raw_event_hash,
            "STALE_QUOTE",
            (quote,),
            mutation_events,
        )
    if quote.condition != QuoteCondition.NORMAL:
        return TradeClassification(
            trade,
            AggressorSide.UNKNOWN,
            AggressorMethod.UNKNOWN,
            quote.raw_event_hash,
            f"QUOTE_CONDITION_{quote.condition.value}",
            (quote,),
            mutation_events,
        )

    if trade.price >= quote.ask_price:
        side = AggressorSide.BUY
        reason = "TRADE_AT_OR_ABOVE_ASK"
    elif trade.price <= quote.bid_price:
        side = AggressorSide.SELL
        reason = "TRADE_AT_OR_BELOW_BID"
    else:
        side = AggressorSide.UNKNOWN
        reason = "TRADE_INSIDE_SPREAD"

    method = (
        AggressorMethod.QUOTE_INFERRED if side != AggressorSide.UNKNOWN else AggressorMethod.UNKNOWN
    )
    return TradeClassification(
        trade, side, method, quote.raw_event_hash, reason, (quote,), mutation_events
    )


def classify_trade_from_ledger(
    trade: TradeEvent,
    quotes: Iterable[QuoteEvent],
    *,
    ledger_snapshot: TradeLedgerSnapshot,
    max_quote_age: timedelta,
) -> TradeClassification:
    """Classify an active ledger trade while retaining every NEW/CORRECT revision."""
    if not isinstance(ledger_snapshot, TradeLedgerSnapshot):
        raise TypeError("ledger_snapshot must be TradeLedgerSnapshot")
    mutations = ledger_snapshot.mutations_for_active_trade(trade)
    return classify_trade(
        trade,
        quotes,
        max_quote_age=max_quote_age,
        supporting_mutations=mutations,
    )


def aggregate_trade_flow(
    classifications: Iterable[TradeClassification],
    *,
    instrument_id: str,
    session_id: str,
    start_utc: datetime,
    end_utc: datetime,
    additional_lineage_events: Iterable[LineageEvent] = (),
) -> FlowWindow:
    """Aggregate a half-open [start, end) interval without guessing unknown side."""
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise ValueError("window boundaries must be timezone-aware")
    if start_utc.utcoffset() != timedelta(0) or end_utc.utcoffset() != timedelta(0):
        raise ValueError("window boundaries must be UTC")
    if end_utc <= start_utc:
        raise ValueError("end_utc must be after start_utc")
    if not instrument_id or not session_id:
        raise ValueError("instrument_id and session_id must be non-empty")

    selected = [
        item
        for item in classifications
        if item.trade.instrument_id == instrument_id
        and start_utc <= item.trade.event_time_utc < end_utc
    ]
    buy = sum(
        (item.trade.quantity for item in selected if item.side == AggressorSide.BUY),
        Decimal("0"),
    )
    sell = sum(
        (item.trade.quantity for item in selected if item.side == AggressorSide.SELL),
        Decimal("0"),
    )
    unknown = sum(
        (item.trade.quantity for item in selected if item.side == AggressorSide.UNKNOWN),
        Decimal("0"),
    )
    total = buy + sell + unknown
    exchange_buy = sum(
        (
            item.trade.quantity
            for item in selected
            if item.side == AggressorSide.BUY and item.method == AggressorMethod.EXCHANGE_FLAG
        ),
        Decimal("0"),
    )
    exchange_sell = sum(
        (
            item.trade.quantity
            for item in selected
            if item.side == AggressorSide.SELL and item.method == AggressorMethod.EXCHANGE_FLAG
        ),
        Decimal("0"),
    )
    quote_buy = sum(
        (
            item.trade.quantity
            for item in selected
            if item.side == AggressorSide.BUY and item.method == AggressorMethod.QUOTE_INFERRED
        ),
        Decimal("0"),
    )
    quote_sell = sum(
        (
            item.trade.quantity
            for item in selected
            if item.side == AggressorSide.SELL and item.method == AggressorMethod.QUOTE_INFERRED
        ),
        Decimal("0"),
    )
    classified_count = sum(item.side != AggressorSide.UNKNOWN for item in selected)
    unknown_count = len(selected) - classified_count
    coverage = (buy + sell) / total if total > 0 else Decimal("0")
    lineage_events = [item.trade for item in selected]
    extra_events = tuple(additional_lineage_events)
    if any(event.instrument_id != instrument_id for event in extra_events):
        raise ValueError("additional lineage events must match the flow instrument")
    lineage_events.extend(extra_events)
    unresolved_quote_hashes: list[str] = []
    for item in selected:
        lineage_events.extend(item.supporting_quote_events)
        lineage_events.extend(item.supporting_mutation_events)
        lineage_events.extend(
            mutation.replacement_trade
            for mutation in item.supporting_mutation_events
            if mutation.replacement_trade is not None
        )
        if item.quote_hash is not None and not item.supporting_quote_events:
            unresolved_quote_hashes.append(item.quote_hash)
    input_lineage = InputLineage.from_events(
        lineage_events,
        unresolved_hashes=unresolved_quote_hashes,
    )

    return FlowWindow(
        instrument_id=instrument_id,
        session_id=session_id,
        start_utc=start_utc,
        end_utc=end_utc,
        trade_count=len(selected),
        classified_trade_count=classified_count,
        unknown_trade_count=unknown_count,
        total_quantity=total,
        buy_quantity=buy,
        sell_quantity=sell,
        unknown_quantity=unknown,
        exchange_flag_buy_quantity=exchange_buy,
        exchange_flag_sell_quantity=exchange_sell,
        quote_inferred_buy_quantity=quote_buy,
        quote_inferred_sell_quantity=quote_sell,
        exchange_flag_delta=exchange_buy - exchange_sell,
        quote_inferred_delta=quote_buy - quote_sell,
        delta=buy - sell,
        classified_coverage=coverage,
        input_lineage=input_lineage,
    )


def compute_cvd(windows: Iterable[FlowWindow]) -> tuple[CvdPoint, ...]:
    """Cumulative delta resets at every session boundary.

    Input must already be chronological. Reordering is rejected rather than
    silently repaired, preserving event-time and replay semantics.
    """
    points: list[CvdPoint] = []
    previous_end: datetime | None = None
    previous_instrument: str | None = None
    previous_session: str | None = None
    running = Decimal("0")

    for window in windows:
        if previous_instrument is not None and window.instrument_id != previous_instrument:
            raise ValueError("compute_cvd accepts one instrument per ordered series")
        if previous_end is not None and window.start_utc < previous_end:
            raise ValueError("CVD windows must be chronological and non-overlapping")
        if window.session_id != previous_session:
            running = Decimal("0")
        running += window.delta
        points.append(
            CvdPoint(
                instrument_id=window.instrument_id,
                session_id=window.session_id,
                start_utc=window.start_utc,
                end_utc=window.end_utc,
                delta=window.delta,
                cvd=running,
            )
        )
        previous_end = window.end_utc
        previous_instrument = window.instrument_id
        previous_session = window.session_id

    return tuple(points)


def price_progress_ticks(
    start_price: Decimal,
    end_price: Decimal,
    instrument: InstrumentMetadata,
) -> Decimal:
    """Signed net price progress in contract ticks; positive means upward."""
    if not start_price.is_finite() or not end_price.is_finite():
        raise ValueError("prices must be finite")
    if start_price <= 0 or end_price <= 0:
        raise ValueError("prices must be positive")
    if start_price % instrument.tick_size != 0 or end_price % instrument.tick_size != 0:
        raise ValueError("prices must align to contract tick_size")
    return (end_price - start_price) / instrument.tick_size
