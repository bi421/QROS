from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from researchos.quant_engine.order_flow.contracts import (
    AggressorMethod,
    AggressorSide,
    BookEventKind,
    BookOperation,
    BookSide,
    DatasetManifest,
    FeedType,
    InstrumentMetadata,
    L2BookEvent,
    LicenseStatus,
    QuoteCondition,
    QuoteEvent,
    TradeEvent,
)


NOW = datetime(2026, 11, 2, 4, 0, tzinfo=timezone.utc)
HASH = "a" * 64


def instrument(**overrides: object) -> InstrumentMetadata:
    values: dict[str, object] = {
        "instrument_id": "GCZ6",
        "instrument_root": "GC",
        "contract_month": "202612",
        "currency": "USD",
        "tick_size": Decimal("0.1"),
        "tick_value": Decimal("10"),
        "multiplier": Decimal("100"),
    }
    values.update(overrides)
    return InstrumentMetadata(**values)  # type: ignore[arg-type]


def trade(**overrides: object) -> TradeEvent:
    values: dict[str, object] = {
        "source_id": "synthetic-feed",
        "dataset_id": "synthetic-v1",
        "instrument_id": "GCZ6",
        "event_time_utc": NOW,
        "receive_time_utc": NOW + timedelta(milliseconds=2),
        "price": Decimal("2400.1"),
        "quantity": Decimal("3"),
        "raw_event_hash": HASH,
    }
    values.update(overrides)
    return TradeEvent(**values)  # type: ignore[arg-type]


def quote(**overrides: object) -> QuoteEvent:
    values: dict[str, object] = {
        "source_id": "synthetic-feed",
        "dataset_id": "synthetic-v1",
        "instrument_id": "GCZ6",
        "event_time_utc": NOW,
        "receive_time_utc": NOW + timedelta(milliseconds=2),
        "bid_price": Decimal("2400.0"),
        "ask_price": Decimal("2400.1"),
        "raw_event_hash": HASH,
    }
    values.update(overrides)
    return QuoteEvent(**values)  # type: ignore[arg-type]


def l2(**overrides: object) -> L2BookEvent:
    values: dict[str, object] = {
        "source_id": "synthetic-feed",
        "dataset_id": "synthetic-v1",
        "instrument_id": "GCZ6",
        "event_time_utc": NOW,
        "receive_time_utc": NOW + timedelta(milliseconds=2),
        "sequence_number": 101,
        "price": Decimal("2400.0"),
        "side": BookSide.BID,
        "operation": BookOperation.ADD,
        "quantity": Decimal("5"),
        "event_kind": BookEventKind.DELTA,
        "raw_event_hash": HASH,
    }
    values.update(overrides)
    return L2BookEvent(**values)  # type: ignore[arg-type]


def test_instrument_metadata_is_immutable_and_positive() -> None:
    item = instrument()
    assert item.tick_size == Decimal("0.1")
    with pytest.raises(FrozenInstanceError):
        item.tick_size = Decimal("0.01")  # type: ignore[misc]
    with pytest.raises(ValueError, match="tick_size must be > 0"):
        instrument(tick_size=Decimal("0"))
    with pytest.raises(TypeError, match="finite Decimal"):
        instrument(tick_value=10.0)  # type: ignore[arg-type]


def test_trade_unknown_side_is_preserved_not_guessed() -> None:
    event = trade()
    assert event.aggressor_side == AggressorSide.UNKNOWN
    assert event.aggressor_method == AggressorMethod.UNKNOWN


def test_trade_rejects_side_without_classification_method() -> None:
    with pytest.raises(ValueError, match="UNKNOWN aggressor_method"):
        trade(aggressor_side=AggressorSide.BUY)


def test_trade_accepts_documented_exchange_side_and_validates_tick() -> None:
    event = trade(aggressor_side=AggressorSide.BUY, aggressor_method=AggressorMethod.EXCHANGE_FLAG)
    event.validate_tick(instrument())
    with pytest.raises(ValueError, match="tick_size"):
        trade(price=Decimal("2400.15")).validate_tick(instrument())


def test_trade_rejects_nonpositive_quantity_and_receive_time_before_event() -> None:
    with pytest.raises(ValueError, match="quantity must be > 0"):
        trade(quantity=Decimal("0"))
    with pytest.raises(ValueError, match="cannot precede"):
        trade(receive_time_utc=NOW - timedelta(seconds=1))


def test_trade_rejects_naive_timestamp_and_invalid_hash() -> None:
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        trade(event_time_utc=datetime(2026, 11, 2))
    with pytest.raises(ValueError, match="SHA-256"):
        trade(raw_event_hash="not-a-hash")


def test_quote_normal_locked_crossed_and_stale_conditions() -> None:
    assert quote().condition == QuoteCondition.NORMAL
    assert quote(
        bid_price=Decimal("2400.1"), ask_price=Decimal("2400.1"), condition=QuoteCondition.LOCKED
    )
    assert quote(
        bid_price=Decimal("2400.2"), ask_price=Decimal("2400.1"), condition=QuoteCondition.CROSSED
    )
    assert quote(condition=QuoteCondition.STALE)
    with pytest.raises(ValueError, match="CROSSED condition"):
        quote(
            bid_price=Decimal("2400.0"),
            ask_price=Decimal("2400.1"),
            condition=QuoteCondition.CROSSED,
        )


def test_quote_size_is_optional_but_never_negative() -> None:
    assert quote(bid_size=None, ask_size=Decimal("4")).ask_size == Decimal("4")
    with pytest.raises(ValueError, match="bid_size must be >= 0"):
        quote(bid_size=Decimal("-1"))


def test_quote_tick_validation_checks_both_sides() -> None:
    quote().validate_tick(instrument())
    with pytest.raises(ValueError, match="tick_size"):
        quote(ask_price=Decimal("2400.15")).validate_tick(instrument())


def test_l2_add_change_delete_semantics() -> None:
    assert l2().operation == BookOperation.ADD
    assert l2(operation=BookOperation.CHANGE).quantity == Decimal("5")
    assert l2(operation=BookOperation.DELETE, quantity=Decimal("0"))
    with pytest.raises(ValueError, match="DELETE operation"):
        l2(operation=BookOperation.DELETE, quantity=Decimal("1"))
    with pytest.raises(ValueError, match="ADD/CHANGE"):
        l2(operation=BookOperation.CHANGE, quantity=Decimal("0"))


def test_l2_requires_sequence_and_valid_tick() -> None:
    l2().validate_tick(instrument())
    with pytest.raises(TypeError, match="sequence_number"):
        l2(sequence_number=None)
    with pytest.raises(ValueError, match="tick_size"):
        l2(price=Decimal("2400.05")).validate_tick(instrument())


def _manifest(
    *,
    license_status: LicenseStatus = LicenseStatus.UNVERIFIED,
    feed_type: FeedType = FeedType.TRADES,
    raw_hash: str = HASH,
) -> DatasetManifest:
    return DatasetManifest(
        dataset_id="synthetic-v1",
        dataset_version="1",
        source_id="synthetic-feed",
        vendor="fixture",
        venue="SYNTHETIC",
        product_code="GC",
        instrument=instrument(),
        feed_type=feed_type,
        coverage_start_utc=NOW - timedelta(days=1),
        coverage_end_utc=NOW + timedelta(days=1),
        trading_calendar_version="synthetic-calendar-v1",
        timezone="UTC",
        timestamp_semantics="synthetic UTC event time",
        sequence_semantics="monotonic integer",
        aggregation_semantics="one record per trade",
        aggressor_side_semantics="unknown by default",
        correction_cancel_semantics="not represented",
        snapshot_recovery_semantics="not applicable",
        license_reference="synthetic-fixture",
        license_status=license_status,
        raw_artifact_uri="synthetic://fixture",
        schema_version="1.0",
        acquisition_code_revision="test",
        raw_artifact_sha256=raw_hash,
    )


def test_dataset_manifest_requires_verified_license_for_real_data() -> None:
    assert (
        _manifest(license_status=LicenseStatus.UNVERIFIED).eligible_for_real_data_research is False
    )
    assert (
        _manifest(license_status=LicenseStatus.NOT_REQUIRED).eligible_for_real_data_research
        is False
    )
    assert _manifest(license_status=LicenseStatus.VERIFIED).eligible_for_real_data_research is True


def test_manifest_rejects_invalid_artifact_hash() -> None:
    with pytest.raises(ValueError, match="raw_artifact_sha256"):
        _manifest(raw_hash="bad")


def test_manifest_binds_event_identity_coverage_and_feed_type() -> None:
    manifest = _manifest()
    manifest.validate_trade_event(trade())
    with pytest.raises(ValueError, match="source_id"):
        manifest.validate_trade_event(trade(source_id="other-source"))
    with pytest.raises(ValueError, match="coverage"):
        manifest.validate_trade_event(
            trade(
                event_time_utc=NOW + timedelta(days=2),
                receive_time_utc=NOW + timedelta(days=2, seconds=1),
            )
        )
    with pytest.raises(ValueError, match="TOP_OF_BOOK"):
        manifest.validate_quote_event(quote())


def test_not_required_license_status_does_not_authorize_real_feed() -> None:
    assert (
        _manifest(license_status=LicenseStatus.NOT_REQUIRED).eligible_for_real_data_research
        is False
    )
