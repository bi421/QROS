from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Iterable, Mapping
from researchos.quant_engine.order_flow.contracts import AggressorMethod, AggressorSide
from researchos.quant_engine.order_flow.features import FlowWindow, TradeClassification


class FlowSource(str, Enum):
    EXCHANGE_FLAG = "EXCHANGE_FLAG"
    QUOTE_INFERRED = "QUOTE_INFERRED"


class FootprintState(str, Enum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    HIGH_AGGRESSION_HIGH_PROGRESS = "HIGH_AGGRESSION_HIGH_PROGRESS"
    HIGH_AGGRESSION_LOW_PROGRESS = "HIGH_AGGRESSION_LOW_PROGRESS"
    LOW_AGGRESSION_HIGH_PROGRESS = "LOW_AGGRESSION_HIGH_PROGRESS"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class DetectorDefinition:
    version: str = "0.1.0"
    large_print_percentile: Decimal = Decimal("0.99")
    minimum_reference_count: int = 100
    cluster_window: timedelta = timedelta(seconds=5)
    cluster_minimum_prints: int = 3
    cluster_minimum_quantity: Decimal = Decimal("20")
    minimum_classified_coverage: Decimal = Decimal("0.80")
    high_aggression_ratio: Decimal = Decimal("0.60")
    low_progress_volatility_multiple: Decimal = Decimal("0.25")
    high_progress_volatility_multiple: Decimal = Decimal("1.0")
    absorption_minimum_tests: int = 2
    sweep_response_window: timedelta = timedelta(seconds=5)

    def __post_init__(self):
        if not self.version.strip() or not Decimal("0") < self.large_print_percentile <= 1:
            raise ValueError("invalid version or large-print percentile")
        if self.minimum_reference_count < 1 or self.cluster_minimum_prints < 2:
            raise ValueError("invalid minimum counts")
        if self.cluster_window <= timedelta(0) or self.sweep_response_window <= timedelta(0):
            raise ValueError("windows must be positive")
        if self.cluster_minimum_quantity <= 0 or not 0 <= self.minimum_classified_coverage <= 1:
            raise ValueError("invalid quantity or coverage threshold")
        if not 0 < self.high_aggression_ratio <= 1 or self.low_progress_volatility_multiple < 0:
            raise ValueError("invalid aggression/progress threshold")
        if (
            self.high_progress_volatility_multiple <= self.low_progress_volatility_multiple
            or self.absorption_minimum_tests < 2
        ):
            raise ValueError("invalid normalized progress/test threshold")

    @property
    def definition_id(self):
        payload = {
            k: str(v)
            for k, v in (
                ("version", self.version),
                ("large_print_percentile", self.large_print_percentile),
                ("minimum_reference_count", self.minimum_reference_count),
                ("cluster_window_us", int(self.cluster_window.total_seconds() * 1_000_000)),
                ("cluster_minimum_prints", self.cluster_minimum_prints),
                ("cluster_minimum_quantity", self.cluster_minimum_quantity),
                ("minimum_classified_coverage", self.minimum_classified_coverage),
                ("high_aggression_ratio", self.high_aggression_ratio),
                ("low_progress_volatility_multiple", self.low_progress_volatility_multiple),
                ("high_progress_volatility_multiple", self.high_progress_volatility_multiple),
                ("absorption_minimum_tests", self.absorption_minimum_tests),
                (
                    "sweep_response_window_us",
                    int(self.sweep_response_window.total_seconds() * 1_000_000),
                ),
            )
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class SizeReference:
    cohort_id: str
    quantity_threshold: Decimal
    percentile: Decimal
    reference_count: int
    reference_end_utc: datetime

    def __post_init__(self):
        if self.reference_end_utc.tzinfo is None or self.reference_end_utc.utcoffset() != timedelta(
            0
        ):
            raise ValueError("reference_end_utc must be timezone-aware UTC")
        if (
            not self.cohort_id.strip()
            or self.quantity_threshold <= 0
            or not 0 < self.percentile <= 1
            or self.reference_count < 0
        ):
            raise ValueError("invalid size reference")


@dataclass(frozen=True, slots=True)
class LargePrintCandidate:
    trade_hash: str
    instrument_id: str
    event_time_utc: datetime
    quantity: Decimal
    side: AggressorSide
    method: AggressorMethod
    cohort_id: str
    percentile: Decimal
    reference_count: int
    reference_end_utc: datetime
    definition_id: str


@dataclass(frozen=True, slots=True)
class LargeTradeCluster:
    instrument_id: str
    start_utc: datetime
    end_utc: datetime
    print_count: int
    total_quantity: Decimal
    buy_quantity: Decimal
    sell_quantity: Decimal
    unknown_quantity: Decimal
    side: AggressorSide
    member_trade_hashes: tuple[str, ...]
    definition_id: str


@dataclass(frozen=True, slots=True)
class FlowResponse:
    instrument_id: str
    session_id: str
    start_utc: datetime
    end_utc: datetime
    source: FlowSource
    aggressive_buy_quantity: Decimal
    aggressive_sell_quantity: Decimal
    classified_coverage: Decimal
    price_progress_ticks: Decimal
    trailing_volatility_ticks: Decimal
    volatility_as_of_utc: datetime
    normalized_price_progress: Decimal
    state: FootprintState
    definition_id: str


@dataclass(frozen=True, slots=True)
class AbsorptionCandidate:
    instrument_id: str
    session_id: str
    side: AggressorSide
    contested_level: Decimal
    contested_level_available_at_utc: datetime
    test_count: int
    start_utc: datetime
    end_utc: datetime
    supporting_flow_windows: tuple[tuple[datetime, datetime], ...]
    label: str
    definition_id: str


@dataclass(frozen=True, slots=True)
class ReferenceLevel:
    level_id: str
    instrument_id: str
    price: Decimal
    kind: str
    available_at_utc: datetime
    source: str


@dataclass(frozen=True, slots=True)
class SweepObservation:
    reference: ReferenceLevel
    trade_through_time_utc: datetime
    trade_through_price: Decimal
    trade_through_quantity: Decimal
    response_end_utc: datetime
    response_price: Decimal


@dataclass(frozen=True, slots=True)
class LiquiditySweepCandidate:
    level_id: str
    instrument_id: str
    direction: str
    level_price: Decimal
    trade_through_quantity: Decimal
    response_window_elapsed: timedelta
    response_ticks: Decimal
    response: str
    definition_id: str


def detect_unusually_large_prints(
    classifications: Iterable[TradeClassification],
    references: Mapping[str, SizeReference],
    definition: DetectorDefinition,
) -> tuple[LargePrintCandidate, ...]:
    """D01: supplied reference must be computed only from prior cohort data."""
    out = []
    for item in classifications:
        t, ref = item.trade, references.get(item.trade.raw_event_hash)
        if (
            ref is None
            or ref.reference_count < definition.minimum_reference_count
            or ref.percentile < definition.large_print_percentile
            or t.quantity < ref.quantity_threshold
            or ref.reference_end_utc >= t.event_time_utc
        ):
            continue
        out.append(
            LargePrintCandidate(
                t.raw_event_hash,
                t.instrument_id,
                t.event_time_utc,
                t.quantity,
                item.side,
                item.method,
                ref.cohort_id,
                ref.percentile,
                ref.reference_count,
                ref.reference_end_utc,
                definition.definition_id,
            )
        )
    return tuple(sorted(out, key=lambda x: (x.event_time_utc, x.trade_hash)))


def detect_large_trade_clusters(
    candidates: Iterable[LargePrintCandidate], definition: DetectorDefinition
) -> tuple[LargeTradeCluster, ...]:
    """D02: non-overlapping windows anchored at each first qualifying print."""
    rows = sorted(candidates, key=lambda x: (x.instrument_id, x.event_time_utc, x.trade_hash))
    out, i = [], 0
    while i < len(rows):
        first, cutoff = rows[i], rows[i].event_time_utc + definition.cluster_window
        j = i
        while (
            j < len(rows)
            and rows[j].instrument_id == first.instrument_id
            and rows[j].event_time_utc < cutoff
        ):
            j += 1
        group = rows[i:j]
        total = sum((x.quantity for x in group), Decimal(0))
        if (
            len(group) >= definition.cluster_minimum_prints
            and total >= definition.cluster_minimum_quantity
        ):
            buy = sum((x.quantity for x in group if x.side == AggressorSide.BUY), Decimal(0))
            sell = sum((x.quantity for x in group if x.side == AggressorSide.SELL), Decimal(0))
            unknown = sum(
                (x.quantity for x in group if x.side == AggressorSide.UNKNOWN), Decimal(0)
            )
            side = (
                AggressorSide.BUY
                if buy > 0 and sell == unknown == 0
                else AggressorSide.SELL
                if sell > 0 and buy == unknown == 0
                else AggressorSide.UNKNOWN
            )
            out.append(
                LargeTradeCluster(
                    first.instrument_id,
                    first.event_time_utc,
                    group[-1].event_time_utc,
                    len(group),
                    total,
                    buy,
                    sell,
                    unknown,
                    side,
                    tuple(x.trade_hash for x in group),
                    definition.definition_id,
                )
            )
            i = j
        else:
            i += 1
    return tuple(out)


def classify_aggression_price_response(
    flow: FlowWindow,
    *,
    source: FlowSource,
    price_progress_ticks: Decimal,
    trailing_volatility_ticks: Decimal,
    volatility_as_of_utc: datetime,
    definition: DetectorDefinition,
) -> FlowResponse:
    """D05: source-separated aggression and signed price response."""
    if trailing_volatility_ticks <= 0:
        raise ValueError("trailing_volatility_ticks must be positive")
    if (
        volatility_as_of_utc.tzinfo is None
        or volatility_as_of_utc.utcoffset() != timedelta(0)
        or volatility_as_of_utc > flow.start_utc
    ):
        raise ValueError("volatility estimate must be UTC and available before the flow window")
    buy, sell = (
        (flow.exchange_flag_buy_quantity, flow.exchange_flag_sell_quantity)
        if source == FlowSource.EXCHANGE_FLAG
        else (flow.quote_inferred_buy_quantity, flow.quote_inferred_sell_quantity)
    )
    qty = buy + sell
    coverage = qty / flow.total_quantity if flow.total_quantity > 0 else Decimal(0)
    state = FootprintState.INSUFFICIENT_DATA
    if coverage >= definition.minimum_classified_coverage and qty > 0:
        aggressive = abs(buy - sell) / qty >= definition.high_aggression_ratio
        normalized_progress = abs(price_progress_ticks / trailing_volatility_ticks)
        if aggressive and normalized_progress >= definition.high_progress_volatility_multiple:
            state = FootprintState.HIGH_AGGRESSION_HIGH_PROGRESS
        elif aggressive and normalized_progress <= definition.low_progress_volatility_multiple:
            state = FootprintState.HIGH_AGGRESSION_LOW_PROGRESS
        elif not aggressive and normalized_progress >= definition.high_progress_volatility_multiple:
            state = FootprintState.LOW_AGGRESSION_HIGH_PROGRESS
        else:
            state = FootprintState.OTHER
    return FlowResponse(
        flow.instrument_id,
        flow.session_id,
        flow.start_utc,
        flow.end_utc,
        source,
        buy,
        sell,
        coverage,
        price_progress_ticks,
        trailing_volatility_ticks,
        volatility_as_of_utc,
        price_progress_ticks / trailing_volatility_ticks,
        state,
        definition.definition_id,
    )


def detect_absorption_candidate(
    responses: Iterable[FlowResponse],
    *,
    side: AggressorSide,
    contested_level: Decimal,
    contested_level_available_at_utc: datetime,
    test_count: int,
    definition: DetectorDefinition,
) -> AbsorptionCandidate | None:
    """D06: trade-price absorption pattern only; never asserts hidden liquidity."""
    if side not in (AggressorSide.BUY, AggressorSide.SELL):
        raise ValueError("side must be BUY or SELL")
    if contested_level <= 0 or test_count < 0:
        raise ValueError("invalid level or test_count")
    if (
        contested_level_available_at_utc.tzinfo is None
        or contested_level_available_at_utc.utcoffset() != timedelta(0)
    ):
        raise ValueError("contested level availability must be UTC")
    rows = sorted(
        (
            x
            for x in responses
            if x.state == FootprintState.HIGH_AGGRESSION_LOW_PROGRESS
            and (
                (
                    side == AggressorSide.BUY
                    and x.aggressive_buy_quantity > x.aggressive_sell_quantity
                )
                or (
                    side == AggressorSide.SELL
                    and x.aggressive_sell_quantity > x.aggressive_buy_quantity
                )
            )
        ),
        key=lambda x: (x.start_utc, x.end_utc),
    )
    if not rows or test_count < definition.absorption_minimum_tests:
        return None
    first, last = rows[0], rows[-1]
    if contested_level_available_at_utc > first.start_utc:
        return None
    if any(
        x.instrument_id != first.instrument_id or x.session_id != first.session_id for x in rows
    ):
        return None
    return AbsorptionCandidate(
        first.instrument_id,
        first.session_id,
        side,
        contested_level,
        contested_level_available_at_utc,
        test_count,
        first.start_utc,
        last.end_utc,
        tuple((x.start_utc, x.end_utc) for x in rows),
        "TRADE_PRICE_ABSORPTION_PATTERN",
        definition.definition_id,
    )


def detect_liquidity_sweep_candidate(
    observation: SweepObservation, *, tick_size: Decimal, definition: DetectorDefinition
) -> LiquiditySweepCandidate | None:
    """D08: prior reference + actual trade-through + bounded post-event response."""
    ref = observation.reference
    if tick_size <= 0 or observation.trade_through_quantity <= 0:
        raise ValueError("tick_size and trade-through quantity must be positive")
    if (
        ref.available_at_utc >= observation.trade_through_time_utc
        or observation.response_end_utc < observation.trade_through_time_utc
    ):
        return None
    elapsed = observation.response_end_utc - observation.trade_through_time_utc
    if elapsed > definition.sweep_response_window or ref.price == observation.trade_through_price:
        return None
    if ref.price < observation.trade_through_price:
        direction, move = (
            "ABOVE_REFERENCE",
            (observation.response_price - observation.trade_through_price) / tick_size,
        )
    else:
        direction, move = (
            "BELOW_REFERENCE",
            (observation.trade_through_price - observation.response_price) / tick_size,
        )
    response = "REJECTION" if move < 0 else "ACCEPTANCE"
    return LiquiditySweepCandidate(
        ref.level_id,
        ref.instrument_id,
        direction,
        ref.price,
        observation.trade_through_quantity,
        elapsed,
        move,
        response,
        definition.definition_id,
    )
