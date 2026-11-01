"""Immutable, source-agnostic contracts for institutional-footprint research.

These contracts validate event shape and basic semantics only. They do not
classify participants, infer trading intent, or access market-data feeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
import re

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FeedType(str, Enum):
    TRADES = "TRADES"
    TOP_OF_BOOK = "TOP_OF_BOOK"
    L2_MARKET_BY_PRICE = "L2_MARKET_BY_PRICE"
    BARS = "BARS"


class LicenseStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    NOT_REQUIRED = "NOT_REQUIRED"


class AggressorSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"


class AggressorMethod(str, Enum):
    EXCHANGE_FLAG = "EXCHANGE_FLAG"
    QUOTE_INFERRED = "QUOTE_INFERRED"
    UNKNOWN = "UNKNOWN"


class QuoteCondition(str, Enum):
    NORMAL = "NORMAL"
    LOCKED = "LOCKED"
    CROSSED = "CROSSED"
    STALE = "STALE"


class BookSide(str, Enum):
    BID = "BID"
    ASK = "ASK"


class BookOperation(str, Enum):
    ADD = "ADD"
    CHANGE = "CHANGE"
    DELETE = "DELETE"


class BookEventKind(str, Enum):
    SNAPSHOT = "SNAPSHOT"
    DELTA = "DELTA"


class DataQualityState(str, Enum):
    VALID = "VALID"
    DEGRADED = "DEGRADED"
    INVALID = "INVALID"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


def _non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{field_name} must be a non-empty trimmed string")


def _utc(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")


def _decimal(
    value: Decimal, field_name: str, *, positive: bool = False, non_negative: bool = False
) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise TypeError(f"{field_name} must be a finite Decimal")
    if positive and value <= 0:
        raise ValueError(f"{field_name} must be > 0")
    if non_negative and value < 0:
        raise ValueError(f"{field_name} must be >= 0")


def _sha256(value: str, field_name: str = "raw_event_hash") -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase 64-character SHA-256 hex digest")


def _base_event(
    source_id: str,
    dataset_id: str,
    instrument_id: str,
    event_time_utc: datetime,
    receive_time_utc: datetime,
    raw_event_hash: str,
) -> None:
    _non_empty(source_id, "source_id")
    _non_empty(dataset_id, "dataset_id")
    _non_empty(instrument_id, "instrument_id")
    _utc(event_time_utc, "event_time_utc")
    _utc(receive_time_utc, "receive_time_utc")
    if receive_time_utc < event_time_utc:
        raise ValueError("receive_time_utc cannot precede event_time_utc")
    _sha256(raw_event_hash)


@dataclass(frozen=True, slots=True)
class InstrumentMetadata:
    """Exact listed contract metadata; values retain native contract units."""

    instrument_id: str
    instrument_root: str
    contract_month: str
    currency: str
    tick_size: Decimal
    tick_value: Decimal
    multiplier: Decimal

    def __post_init__(self) -> None:
        for name in ("instrument_id", "instrument_root", "contract_month", "currency"):
            _non_empty(getattr(self, name), name)
        for name in ("tick_size", "tick_value", "multiplier"):
            _decimal(getattr(self, name), name, positive=True)


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    """Provenance required before a real feed can be accepted for research."""

    dataset_id: str
    dataset_version: str
    source_id: str
    vendor: str
    venue: str
    product_code: str
    instrument: InstrumentMetadata
    feed_type: FeedType
    coverage_start_utc: datetime
    coverage_end_utc: datetime
    trading_calendar_version: str
    timezone: str
    timestamp_semantics: str
    sequence_semantics: str
    aggregation_semantics: str
    aggressor_side_semantics: str
    correction_cancel_semantics: str
    snapshot_recovery_semantics: str
    license_reference: str
    license_status: LicenseStatus
    raw_artifact_uri: str
    schema_version: str
    acquisition_code_revision: str
    raw_artifact_sha256: str
    known_exclusions: tuple[str, ...] = ()
    vendor_documentation_hash: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "dataset_id",
            "dataset_version",
            "source_id",
            "vendor",
            "venue",
            "product_code",
            "trading_calendar_version",
            "timezone",
            "timestamp_semantics",
            "sequence_semantics",
            "aggregation_semantics",
            "aggressor_side_semantics",
            "correction_cancel_semantics",
            "snapshot_recovery_semantics",
            "license_reference",
            "raw_artifact_uri",
            "schema_version",
            "acquisition_code_revision",
        ):
            _non_empty(getattr(self, name), name)
        if not isinstance(self.instrument, InstrumentMetadata):
            raise TypeError("instrument must be InstrumentMetadata")
        if not isinstance(self.feed_type, FeedType):
            raise TypeError("feed_type must be FeedType")
        if not isinstance(self.license_status, LicenseStatus):
            raise TypeError("license_status must be LicenseStatus")
        _utc(self.coverage_start_utc, "coverage_start_utc")
        _utc(self.coverage_end_utc, "coverage_end_utc")
        if self.coverage_end_utc <= self.coverage_start_utc:
            raise ValueError("coverage_end_utc must be after coverage_start_utc")
        if not isinstance(self.known_exclusions, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in self.known_exclusions
        ):
            raise ValueError("known_exclusions must be a tuple of non-empty strings")
        _sha256(self.raw_artifact_sha256, "raw_artifact_sha256")
        if self.vendor_documentation_hash is not None:
            _sha256(self.vendor_documentation_hash, "vendor_documentation_hash")

    @property
    def eligible_for_real_data_research(self) -> bool:
        return self.license_status == LicenseStatus.VERIFIED

    def _validate_event_identity(self, event: object) -> None:
        if getattr(event, "source_id", None) != self.source_id:
            raise ValueError("event source_id does not match dataset manifest")
        if getattr(event, "dataset_id", None) != self.dataset_id:
            raise ValueError("event dataset_id does not match dataset manifest")
        if getattr(event, "instrument_id", None) != self.instrument.instrument_id:
            raise ValueError("event instrument_id does not match dataset manifest")
        event_time = getattr(event, "event_time_utc", None)
        if not isinstance(event_time, datetime) or not (
            self.coverage_start_utc <= event_time < self.coverage_end_utc
        ):
            raise ValueError("event_time_utc is outside dataset manifest coverage")

    def validate_trade_event(self, event: TradeEvent) -> None:
        if self.feed_type != FeedType.TRADES:
            raise ValueError("trade event requires TRADES feed manifest")
        self._validate_event_identity(event)
        event.validate_tick(self.instrument)

    def validate_quote_event(self, event: QuoteEvent) -> None:
        if self.feed_type != FeedType.TOP_OF_BOOK:
            raise ValueError("quote event requires TOP_OF_BOOK feed manifest")
        self._validate_event_identity(event)
        event.validate_tick(self.instrument)

    def validate_l2_event(self, event: L2BookEvent) -> None:
        if self.feed_type != FeedType.L2_MARKET_BY_PRICE:
            raise ValueError("L2 event requires L2_MARKET_BY_PRICE feed manifest")
        self._validate_event_identity(event)
        event.validate_tick(self.instrument)


@dataclass(frozen=True, slots=True)
class TradeEvent:
    source_id: str
    dataset_id: str
    instrument_id: str
    event_time_utc: datetime
    receive_time_utc: datetime
    price: Decimal
    quantity: Decimal
    raw_event_hash: str
    aggressor_side: AggressorSide = AggressorSide.UNKNOWN
    aggressor_method: AggressorMethod = AggressorMethod.UNKNOWN
    sequence_number: int | str | None = None
    trade_id: str | None = None

    def __post_init__(self) -> None:
        _base_event(
            self.source_id,
            self.dataset_id,
            self.instrument_id,
            self.event_time_utc,
            self.receive_time_utc,
            self.raw_event_hash,
        )
        _decimal(self.price, "price", positive=True)
        _decimal(self.quantity, "quantity", positive=True)
        if not isinstance(self.aggressor_side, AggressorSide):
            raise TypeError("aggressor_side must be AggressorSide")
        if not isinstance(self.aggressor_method, AggressorMethod):
            raise TypeError("aggressor_method must be AggressorMethod")
        if (
            self.aggressor_method == AggressorMethod.UNKNOWN
            and self.aggressor_side != AggressorSide.UNKNOWN
        ):
            raise ValueError("UNKNOWN aggressor_method requires UNKNOWN aggressor_side")
        if (
            self.aggressor_method != AggressorMethod.UNKNOWN
            and self.aggressor_side == AggressorSide.UNKNOWN
        ):
            raise ValueError("classified aggressor_method requires BUY or SELL side")
        if self.sequence_number is not None and (
            isinstance(self.sequence_number, bool)
            or not isinstance(self.sequence_number, (int, str))
            or (isinstance(self.sequence_number, str) and not self.sequence_number)
        ):
            raise ValueError("sequence_number must be a non-empty int/string or None")
        if self.trade_id is not None:
            _non_empty(self.trade_id, "trade_id")

    def validate_tick(self, instrument: InstrumentMetadata) -> None:
        if self.instrument_id != instrument.instrument_id:
            raise ValueError("trade instrument_id does not match contract metadata")
        if self.price % instrument.tick_size != 0:
            raise ValueError("trade price is not aligned to contract tick_size")


@dataclass(frozen=True, slots=True)
class QuoteEvent:
    source_id: str
    dataset_id: str
    instrument_id: str
    event_time_utc: datetime
    receive_time_utc: datetime
    bid_price: Decimal
    ask_price: Decimal
    raw_event_hash: str
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None
    sequence_number: int | str | None = None
    condition: QuoteCondition = QuoteCondition.NORMAL

    def __post_init__(self) -> None:
        _base_event(
            self.source_id,
            self.dataset_id,
            self.instrument_id,
            self.event_time_utc,
            self.receive_time_utc,
            self.raw_event_hash,
        )
        _decimal(self.bid_price, "bid_price", positive=True)
        _decimal(self.ask_price, "ask_price", positive=True)
        if self.bid_price > self.ask_price and self.condition != QuoteCondition.CROSSED:
            raise ValueError("crossed bid/ask requires CROSSED condition")
        if self.bid_price == self.ask_price and self.condition == QuoteCondition.NORMAL:
            raise ValueError("locked bid/ask requires LOCKED condition")
        if self.condition == QuoteCondition.CROSSED and self.bid_price <= self.ask_price:
            raise ValueError("CROSSED condition requires bid_price > ask_price")
        if self.condition == QuoteCondition.LOCKED and self.bid_price != self.ask_price:
            raise ValueError("LOCKED condition requires bid_price == ask_price")
        if self.condition == QuoteCondition.STALE and self.bid_price > self.ask_price:
            raise ValueError("stale quote cannot be crossed")
        for name in ("bid_size", "ask_size"):
            value = getattr(self, name)
            if value is not None:
                _decimal(value, name, non_negative=True)
        if not isinstance(self.condition, QuoteCondition):
            raise TypeError("condition must be QuoteCondition")
        if self.sequence_number is not None and (
            isinstance(self.sequence_number, bool)
            or not isinstance(self.sequence_number, (int, str))
            or (isinstance(self.sequence_number, str) and not self.sequence_number)
        ):
            raise ValueError("sequence_number must be a non-empty int/string or None")

    def validate_tick(self, instrument: InstrumentMetadata) -> None:
        if self.instrument_id != instrument.instrument_id:
            raise ValueError("quote instrument_id does not match contract metadata")
        if self.bid_price % instrument.tick_size != 0 or self.ask_price % instrument.tick_size != 0:
            raise ValueError("quote price is not aligned to contract tick_size")


@dataclass(frozen=True, slots=True)
class L2BookEvent:
    source_id: str
    dataset_id: str
    instrument_id: str
    event_time_utc: datetime
    receive_time_utc: datetime
    sequence_number: int | str
    price: Decimal
    side: BookSide
    operation: BookOperation
    quantity: Decimal
    event_kind: BookEventKind
    raw_event_hash: str

    def __post_init__(self) -> None:
        _base_event(
            self.source_id,
            self.dataset_id,
            self.instrument_id,
            self.event_time_utc,
            self.receive_time_utc,
            self.raw_event_hash,
        )
        if isinstance(self.sequence_number, bool) or not isinstance(
            self.sequence_number, (int, str)
        ):
            raise TypeError("L2 sequence_number must be int or str")
        if isinstance(self.sequence_number, str) and not self.sequence_number:
            raise ValueError("L2 sequence_number cannot be empty")
        _decimal(self.price, "price", positive=True)
        _decimal(self.quantity, "quantity", non_negative=True)
        if self.operation == BookOperation.DELETE and self.quantity != 0:
            raise ValueError("DELETE operation requires quantity == 0")
        if self.operation != BookOperation.DELETE and self.quantity <= 0:
            raise ValueError("ADD/CHANGE operation requires quantity > 0")
        if not isinstance(self.side, BookSide) or not isinstance(self.operation, BookOperation):
            raise TypeError("side and operation must use their enum types")
        if not isinstance(self.event_kind, BookEventKind):
            raise TypeError("event_kind must be BookEventKind")

    def validate_tick(self, instrument: InstrumentMetadata) -> None:
        if self.instrument_id != instrument.instrument_id:
            raise ValueError("L2 instrument_id does not match contract metadata")
        if self.price % instrument.tick_size != 0:
            raise ValueError("L2 price is not aligned to contract tick_size")
