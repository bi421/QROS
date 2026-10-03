"""
Comprehensive test suite for the Data Engine (Phase 1).

Tests cover:
    - Candle, Tick, Quote, Trade, OrderBook models
    - Deterministic IDs and hashing
    - Serialization round-trips
    - HistoricalDataset lifecycle
    - DatasetMetadata
    - CSV Loader
    - DatasetValidator (gaps, duplicates, outliers)
    - DatasetRepository (in-memory and SQLite)
    - HistoricalIterator
    - RangeQuery and MultiSymbolQuery
    - Timezone normalization
    - Hashing and versioning
"""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from researchos.data_engine import (
    Candle,
    CandleField,
    CsvLoader,
    DataQuality,
    DatasetMetadata,
    DatasetRepository,
    DatasetStatus,
    DatasetValidator,
    DatasetVersion,
    DuplicateDetector,
    GapDetector,
    HistoricalDataset,
    HistoricalIterator,
    LoaderConfig,
    MissingCandleDetector,
    MultiSymbolQuery,
    OrderBook,
    OrderBookLevel,
    OutlierDetector,
    Quote,
    RangeQuery,
    SqliteDatasetRepository,
    Tick,
    Timeframe,
    Trade,
    ValidationReport,
    bump_dataset_version,
    compute_candle_hash,
    compute_dataset_hash,
    compute_range_hash,
    compute_record_hash,
    convert_timezone,
    format_iso,
    normalize_timestamp,
    parse_iso,
    verify_dataset_integrity,
)

# =============================================================================
# Helper fixtures
# =============================================================================


@pytest.fixture
def candle() -> Candle:
    return Candle(
        symbol="XAU/USD",
        timeframe="1h",
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        open=2000.0,
        high=2010.0,
        low=1995.0,
        close=2005.0,
        volume=1000.0,
    )


@pytest.fixture
def tick() -> Tick:
    return Tick(
        symbol="XAU/USD",
        timestamp=datetime(2024, 1, 1, 12, 0, 0, 500000, tzinfo=timezone.utc),
        price=2005.50,
        volume=10.0,
        side="buy",
        bid=2005.0,
        ask=2006.0,
    )


@pytest.fixture
def quote() -> Quote:
    return Quote(
        symbol="XAU/USD",
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        bid=2005.0,
        ask=2006.0,
        bid_size=15.0,
        ask_size=10.0,
    )


@pytest.fixture
def trade() -> Trade:
    return Trade(
        symbol="XAU/USD",
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        price=2005.50,
        volume=20.0,
        side="buy",
        trade_id="TRADE123",
    )


@pytest.fixture
def orderbook() -> OrderBook:
    return OrderBook(
        symbol="XAU/USD",
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        bids=[
            OrderBookLevel(price=2005.0, size=10.0, order_count=3),
            OrderBookLevel(price=2004.0, size=20.0, order_count=5),
        ],
        asks=[
            OrderBookLevel(price=2006.0, size=15.0, order_count=4),
            OrderBookLevel(price=2007.0, size=25.0, order_count=6),
        ],
    )


@pytest.fixture
def sample_candles() -> list:
    """Create deterministic sample candles for testing."""
    base_time = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    candles = []
    for i in range(10):
        candles.append(
            Candle(
                symbol="XAU/USD",
                timeframe="1h",
                timestamp=base_time + timedelta(hours=i),
                open=2000.0 + i,
                high=2010.0 + i,
                low=1995.0 + i,
                close=2005.0 + i,
                volume=1000.0 + i * 100,
            )
        )
    return candles


@pytest.fixture
def sample_dataset(sample_candles) -> HistoricalDataset:
    ds = HistoricalDataset(
        symbol="XAU/USD",
        timeframe="1h",
        data_type="candle",
        source="test",
        records=sample_candles,
    )
    ds.mark_ready()
    return ds


# =============================================================================
# Test: Candle
# =============================================================================


class TestCandle:
    def test_create_candle(self, candle):
        assert candle.symbol == "XAU/USD"
        assert candle.timeframe == "1h"
        assert candle.open == 2000.0
        assert candle.high == 2010.0
        assert candle.low == 1995.0
        assert candle.close == 2005.0
        assert candle.volume == 1000.0
        assert candle.is_bullish is True
        assert candle.is_bearish is False
        assert candle.range == 15.0
        assert candle.body == 5.0
        assert candle.upper_wick == 5.0
        assert candle.lower_wick == 5.0

    def test_candle_deterministic_id(self, candle):
        c2 = Candle(
            symbol="XAU/USD",
            timeframe="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=2000.0,
            high=2010.0,
            low=1995.0,
            close=2005.0,
            volume=1000.0,
        )
        assert candle.id == c2.id

    def test_candle_serialization_roundtrip(self, candle):
        data = candle.to_dict()
        c2 = Candle.from_dict(data)
        assert candle.id == c2.id
        assert candle.symbol == c2.symbol
        assert candle.open == c2.open
        assert candle.close == c2.close
        assert candle.timestamp == c2.timestamp

    def test_candle_bearish(self):
        c = Candle(
            symbol="XAU/USD",
            timeframe="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=2010.0,
            high=2015.0,
            low=2000.0,
            close=2005.0,
            volume=1000.0,
        )
        assert c.is_bearish is True
        assert c.is_bullish is False
        assert c.body == 5.0

    def test_candle_typical_price(self, candle):
        expected = (2010.0 + 1995.0 + 2005.0) / 3.0
        assert candle.typical_price == expected

    def test_candle_json(self, candle):
        json_str = candle.to_json()
        data = json.loads(json_str)
        assert data["symbol"] == "XAU/USD"
        assert data["timeframe"] == "1h"


class TestCandleExtendedFields:
    """Tests for the optional MT5-compatible candle fields (spread, tick_volume, real_volume)."""

    def test_creation_without_new_fields(self, candle):
        assert candle.spread is None
        assert candle.tick_volume is None
        assert candle.real_volume is None

    def test_creation_with_spread(self):
        c = Candle(
            symbol="XAU/USD",
            timeframe="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=2000.0,
            high=2010.0,
            low=1995.0,
            close=2005.0,
            spread=12.0,
        )
        assert c.spread == 12.0
        assert c.tick_volume is None
        assert c.real_volume is None

    def test_creation_with_tick_volume(self):
        c = Candle(
            symbol="XAU/USD",
            timeframe="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=2000.0,
            high=2010.0,
            low=1995.0,
            close=2005.0,
            tick_volume=34000.0,
        )
        assert c.tick_volume == 34000.0
        assert c.spread is None

    def test_creation_with_real_volume(self):
        c = Candle(
            symbol="XAU/USD",
            timeframe="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=2000.0,
            high=2010.0,
            low=1995.0,
            close=2005.0,
            real_volume=125.5,
        )
        assert c.real_volume == 125.5
        assert c.tick_volume is None

    def test_creation_with_all_new_fields(self):
        c = Candle(
            symbol="XAU/USD",
            timeframe="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=2000.0,
            high=2010.0,
            low=1995.0,
            close=2005.0,
            spread=8.0,
            tick_volume=1000.0,
            real_volume=200.0,
        )
        assert c.spread == 8.0
        assert c.tick_volume == 1000.0
        assert c.real_volume == 200.0

    def test_serialization_roundtrip_with_new_fields(self):
        c = Candle(
            symbol="XAU/USD",
            timeframe="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=2000.0,
            high=2010.0,
            low=1995.0,
            close=2005.0,
            volume=1000.0,
            spread=9.5,
            tick_volume=5000.0,
            real_volume=88.0,
        )
        c2 = Candle.from_dict(c.to_dict())
        assert c2.spread == 9.5
        assert c2.tick_volume == 5000.0
        assert c2.real_volume == 88.0
        assert c2.id == c.id
        assert c2.hash == c.hash

    def test_none_serialization_roundtrip(self, candle):
        data = candle.to_dict()
        assert data["spread"] is None
        assert data["tick_volume"] is None
        assert data["real_volume"] is None
        c2 = Candle.from_dict(data)
        assert c2.spread is None
        assert c2.tick_volume is None
        assert c2.real_volume is None

    def test_hash_stability_without_new_fields(self, candle):
        c2 = Candle(
            symbol="XAU/USD",
            timeframe="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=2000.0,
            high=2010.0,
            low=1995.0,
            close=2005.0,
            volume=1000.0,
        )
        assert candle.hash == c2.hash
        assert len(candle.hash) == 64

    def test_hash_participates_when_fields_set(self, candle):
        with_spread = Candle(
            symbol="XAU/USD",
            timeframe="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=2000.0,
            high=2010.0,
            low=1995.0,
            close=2005.0,
            volume=1000.0,
            spread=5.0,
        )
        without_spread = Candle(
            symbol="XAU/USD",
            timeframe="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=2000.0,
            high=2010.0,
            low=1995.0,
            close=2005.0,
            volume=1000.0,
        )
        assert with_spread.hash != without_spread.hash

    def test_hash_deterministic_with_fields(self):
        def make():
            return Candle(
                symbol="XAU/USD",
                timeframe="1h",
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                open=2000.0,
                high=2010.0,
                low=1995.0,
                close=2005.0,
                volume=1000.0,
                spread=3.0,
                tick_volume=77.0,
                real_volume=11.0,
            )

        assert make().hash == make().hash

    def test_old_dataset_compatibility(self, candle):
        data = candle.to_dict()
        restored = Candle.from_dict(data)
        assert restored.id == candle.id
        assert restored.hash == candle.hash
        assert restored.open == candle.open
        assert restored.timeframe == candle.timeframe

    def test_zero_spread_participates_in_hash(self):
        c_zero = Candle(
            symbol="XAU/USD",
            timeframe="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=2000.0,
            high=2010.0,
            low=1995.0,
            close=2005.0,
            spread=0.0,
        )
        c_none = Candle(
            symbol="XAU/USD",
            timeframe="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=2000.0,
            high=2010.0,
            low=1995.0,
            close=2005.0,
        )
        assert c_zero.spread == 0.0
        assert c_none.spread is None
        assert c_zero.hash != c_none.hash


# =============================================================================
# Test: Tick
# =============================================================================


class TestTick:
    def test_create_tick(self, tick):
        assert tick.symbol == "XAU/USD"
        assert tick.price == 2005.50
        assert tick.side == "buy"
        assert tick.spread == 1.0
        assert tick.mid_price == 2005.5

    def test_tick_deterministic_id(self, tick):
        t2 = Tick(
            symbol="XAU/USD",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, 500000, tzinfo=timezone.utc),
            price=2005.50,
            volume=10.0,
            side="buy",
            bid=2005.0,
            ask=2006.0,
        )
        assert tick.id == t2.id

    def test_tick_serialization_roundtrip(self, tick):
        data = tick.to_dict()
        t2 = Tick.from_dict(data)
        assert tick.id == t2.id
        assert tick.price == t2.price
        assert tick.side == t2.side

    def test_tick_no_spread(self):
        t = Tick(
            symbol="XAU/USD",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            price=2005.0,
            volume=1.0,
        )
        assert t.spread is None
        assert t.mid_price is None


# =============================================================================
# Test: Quote
# =============================================================================


class TestQuote:
    def test_create_quote(self, quote):
        assert quote.symbol == "XAU/USD"
        assert quote.bid == 2005.0
        assert quote.ask == 2006.0
        assert quote.mid == 2005.5
        assert quote.spread == 1.0
        assert quote.spread_bps > 0

    def test_quote_serialization_roundtrip(self, quote):
        data = quote.to_dict()
        q2 = Quote.from_dict(data)
        assert quote.id == q2.id
        assert quote.bid == q2.bid
        assert quote.ask == q2.ask


# =============================================================================
# Test: Trade
# =============================================================================


class TestTrade:
    def test_create_trade(self, trade):
        assert trade.symbol == "XAU/USD"
        assert trade.price == 2005.50
        assert trade.volume == 20.0
        assert trade.side == "buy"
        assert trade.notional == 2005.50 * 20.0
        assert trade.is_buy is True
        assert trade.is_sell is False

    def test_trade_serialization_roundtrip(self, trade):
        data = trade.to_dict()
        t2 = Trade.from_dict(data)
        assert trade.id == t2.id
        assert trade.price == t2.price


# =============================================================================
# Test: OrderBook
# =============================================================================


class TestOrderBook:
    def test_create_orderbook(self, orderbook):
        assert orderbook.symbol == "XAU/USD"
        assert orderbook.best_bid == 2005.0
        assert orderbook.best_ask == 2006.0
        assert orderbook.mid_price == 2005.5
        assert orderbook.spread == 1.0
        assert orderbook.total_bid_size == 30.0
        assert orderbook.total_ask_size == 40.0

    def test_orderbook_serialization_roundtrip(self, orderbook):
        data = orderbook.to_dict()
        ob2 = OrderBook.from_dict(data)
        assert orderbook.id == ob2.id
        assert len(ob2.bids) == 2
        assert len(ob2.asks) == 2


# =============================================================================
# Test: HistoricalDataset
# =============================================================================


class TestHistoricalDataset:
    def test_create_dataset(self, sample_dataset, sample_candles):
        assert sample_dataset.symbol == "XAU/USD"
        assert sample_dataset.timeframe == "1h"
        assert sample_dataset.record_count == 10
        assert sample_dataset.status == DatasetStatus.READY
        assert sample_dataset.start_time is not None
        assert sample_dataset.end_time is not None
        assert sample_dataset.duration_seconds > 0

    def test_dataset_add_records(self):
        ds = HistoricalDataset(symbol="XAU/USD", timeframe="1h")
        assert ds.record_count == 0
        c = Candle(
            symbol="XAU/USD",
            timeframe="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=2000.0,
            high=2010.0,
            low=1995.0,
            close=2005.0,
            volume=1000.0,
        )
        ds.add_record(c)
        assert ds.record_count == 1

    def test_dataset_sort(self):
        ds = HistoricalDataset(symbol="XAU/USD", timeframe="1h")
        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        c1 = Candle(
            symbol="XAU/USD",
            timeframe="1h",
            timestamp=base + timedelta(hours=2),
            open=2000.0,
            high=2010.0,
            low=1995.0,
            close=2005.0,
            volume=1000.0,
        )
        c2 = Candle(
            symbol="XAU/USD",
            timeframe="1h",
            timestamp=base,
            open=2000.0,
            high=2010.0,
            low=1995.0,
            close=2005.0,
            volume=1000.0,
        )
        ds.add_records([c1, c2])
        ds.sort()
        assert ds._records[0].timestamp == base

    def test_dataset_deterministic_hash(self, sample_dataset):
        h = sample_dataset.dataset_hash
        assert len(h) == 64  # SHA-256 hex
        assert verify_dataset_integrity(sample_dataset) is True

    def test_dataset_iteration(self, sample_dataset):
        count = 0
        for record in sample_dataset:
            count += 1
        assert count == 10

    def test_dataset_indexing(self, sample_dataset):
        assert sample_dataset[0] is not None
        assert len(sample_dataset) == 10

    def test_dataset_lifecycle(self):
        ds = HistoricalDataset(symbol="XAU/USD", timeframe="1h")
        assert ds.status == DatasetStatus.PENDING
        ds.mark_ready()
        assert ds.status == DatasetStatus.READY
        ds.mark_validated()
        assert ds.status == DatasetStatus.VALIDATED
        ds.mark_failed("test failure")
        assert ds.status == DatasetStatus.FAILED


# =============================================================================
# Test: DatasetMetadata
# =============================================================================


class TestDatasetMetadata:
    def test_create_metadata(self):
        meta = DatasetMetadata(
            dataset_id="test-id",
            symbol="XAU/USD",
            timeframe="1h",
            record_count=100,
        )
        assert meta.symbol == "XAU/USD"
        assert meta.record_count == 100
        assert meta.duration_days == 0.0

    def test_metadata_with_times(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 2, tzinfo=timezone.utc)
        meta = DatasetMetadata(
            dataset_id="test-id",
            symbol="XAU/USD",
            timeframe="1h",
            record_count=24,
            start_time=start,
            end_time=end,
        )
        assert meta.duration_days == 1.0
        assert meta.avg_records_per_day == 24.0

    def test_metadata_serialization_roundtrip(self):
        meta = DatasetMetadata(
            dataset_id="test-id",
            symbol="XAU/USD",
            timeframe="1h",
            record_count=100,
            tags=["forex", "gold"],
            description="Test dataset",
        )
        data = meta.to_dict()
        meta2 = DatasetMetadata.from_dict(data)
        assert meta.symbol == meta2.symbol
        assert meta.record_count == meta2.record_count
        assert meta.tags == meta2.tags


# =============================================================================
# Test: CSV Loader
# =============================================================================


class TestCsvLoader:
    def test_load_candles_from_text(self):
        csv_text = """timestamp,open,high,low,close,volume
2024-01-01 09:00:00,2000.0,2010.0,1995.0,2005.0,1000.0
2024-01-01 10:00:00,2005.0,2015.0,2000.0,2010.0,1500.0
2024-01-01 11:00:00,2010.0,2020.0,2005.0,2015.0,2000.0"""
        loader = CsvLoader()
        candles = loader.load_candles_from_text(
            csv_text,
            symbol="XAU/USD",
            timeframe="1h",
        )
        assert len(candles) == 3
        assert candles[0].symbol == "XAU/USD"
        assert candles[0].open == 2000.0
        assert candles[0].close == 2005.0

    def test_loader_stats(self):
        csv_text = """timestamp,open,high,low,close,volume
2024-01-01 09:00:00,2000.0,2010.0,1995.0,2005.0,1000.0
2024-01-01 10:00:00,2005.0,2015.0,2000.0,2010.0,1500.0"""
        loader = CsvLoader()
        loader.load_candles_from_text(csv_text, symbol="XAU/USD", timeframe="1h")
        stats = loader.stats
        assert stats["total_rows"] == 2
        assert stats["loaded_rows"] == 2

    def test_load_candles_with_custom_mapping(self):
        csv_text = """date,o,h,l,c,v
2024-01-01 09:00:00,2000.0,2010.0,1995.0,2005.0,1000.0"""
        mapping = CandleField(timestamp="date", open="o", high="h", low="l", close="c", volume="v")
        loader = CsvLoader()
        candles = loader.load_candles_from_text(
            csv_text,
            symbol="XAU/USD",
            timeframe="1h",
            field_mapping=mapping,
        )
        assert len(candles) == 1
        assert candles[0].open == 2000.0

    def test_load_ticks_from_text(self):
        csv_text = """timestamp,price,volume,side,bid,ask
2024-01-01 09:00:00.000,2005.0,10.0,buy,2004.0,2006.0
2024-01-01 09:00:01.000,2006.0,5.0,sell,2005.0,2007.0"""
        loader = CsvLoader()
        ticks = loader.load_ticks_from_text(csv_text, symbol="XAU/USD")
        assert len(ticks) == 2
        assert ticks[0].price == 2005.0
        assert ticks[0].side == "buy"

    def test_load_quotes_from_text(self):
        csv_text = """timestamp,bid,ask,bid_size,ask_size
2024-01-01 09:00:00.000,2005.0,2006.0,10.0,15.0
2024-01-01 09:00:01.000,2006.0,2007.0,12.0,14.0"""
        loader = CsvLoader()
        quotes = loader.load_quotes_from_text(csv_text, symbol="XAU/USD")
        assert len(quotes) == 2
        assert quotes[0].bid == 2005.0
        assert quotes[0].ask == 2006.0

    def test_load_trades_from_text(self):
        csv_text = """timestamp,price,volume,side
2024-01-01 09:00:00.000,2005.0,10.0,buy
2024-01-01 09:00:01.000,2006.0,5.0,sell"""
        loader = CsvLoader()
        trades = loader.load_trades_from_text(csv_text, symbol="XAU/USD")
        assert len(trades) == 2
        assert trades[0].price == 2005.0
        assert trades[0].side == "buy"

    def test_skip_errors(self):
        csv_text = """timestamp,open,high,low,close,volume
2024-01-01 09:00:00,2000.0,2010.0,1995.0,2005.0,1000.0
bad,data,here,too,broken,no
2024-01-01 11:00:00,2010.0,2020.0,2005.0,2015.0,2000.0"""
        config = LoaderConfig(skip_errors=True)
        loader = CsvLoader(config=config)
        candles = loader.load_candles_from_text(csv_text, symbol="XAU/USD", timeframe="1h")
        assert len(candles) == 2

    # Helper methods for loading from text
    def load_ticks_from_text(self, csv_text, symbol):
        return self._csv_loader().load_ticks_from_text(csv_text, symbol)

    def load_quotes_from_text(self, csv_text, symbol):
        return self._csv_loader().load_quotes_from_text(csv_text, symbol)

    def load_trades_from_text(self, csv_text, symbol):
        return self._csv_loader().load_trades_from_text(csv_text, symbol)

    def _csv_loader(self):
        return CsvLoader()


# =============================================================================
# Test: Validator
# =============================================================================


class TestValidator:
    def test_gap_detection(self, sample_candles):
        detector = GapDetector(tolerance_factor=2.0)
        gaps = detector.detect(sample_candles, "1h")
        assert len(gaps) == 0  # No gaps in consecutive hourly data

    def test_gap_detection_with_gaps(self):
        base = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        candles = [
            Candle(
                symbol="XAU/USD",
                timeframe="1h",
                timestamp=base,
                open=2000.0,
                high=2010.0,
                low=1995.0,
                close=2005.0,
                volume=1000.0,
            ),
            Candle(
                symbol="XAU/USD",
                timeframe="1h",
                timestamp=base + timedelta(hours=5),
                open=2010.0,
                high=2020.0,
                low=2005.0,
                close=2015.0,
                volume=1000.0,
            ),
        ]
        detector = GapDetector(tolerance_factor=2.0)
        gaps = detector.detect(candles, "1h")
        assert len(gaps) == 1
        assert gaps[0]["expected_missing"] == 4

    def test_missing_candle_detection(self):
        base = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        candles = [
            Candle(
                symbol="XAU/USD",
                timeframe="1h",
                timestamp=base,
                open=2000.0,
                high=2010.0,
                low=1995.0,
                close=2005.0,
                volume=1000.0,
            ),
            Candle(
                symbol="XAU/USD",
                timeframe="1h",
                timestamp=base + timedelta(hours=3),
                open=2010.0,
                high=2020.0,
                low=2005.0,
                close=2015.0,
                volume=1000.0,
            ),
        ]
        detector = MissingCandleDetector()
        missing = detector.detect(candles, "1h")
        assert len(missing) == 2  # 2 missing hours

    def test_duplicate_detection(self, sample_candles):
        detector = DuplicateDetector()
        # Add a duplicate
        dup = sample_candles[0]
        sample_candles.append(dup)
        duplicates = detector.detect(sample_candles)
        assert len(duplicates) == 1

    def test_price_outlier_detection(self):
        base = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        candles = []
        for i in range(10):
            candles.append(
                Candle(
                    symbol="XAU/USD",
                    timeframe="1h",
                    timestamp=base + timedelta(hours=i),
                    open=2000.0,
                    high=2010.0,
                    low=1995.0,
                    close=2000.0 + i * 0.1,
                    volume=1000.0,
                )
            )
        # Add an outlier
        candles.append(
            Candle(
                symbol="XAU/USD",
                timeframe="1h",
                timestamp=base + timedelta(hours=10),
                open=5000.0,
                high=5010.0,
                low=4995.0,
                close=5005.0,
                volume=1000.0,
            )
        )
        detector = OutlierDetector(z_score_threshold=3.0)
        outliers = detector.detect_price_outliers(candles)
        assert len(outliers) == 1

    def test_volume_outlier_detection(self):
        base = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        candles = []
        for i in range(10):
            candles.append(
                Candle(
                    symbol="XAU/USD",
                    timeframe="1h",
                    timestamp=base + timedelta(hours=i),
                    open=2000.0,
                    high=2010.0,
                    low=1995.0,
                    close=2005.0,
                    volume=1000.0 + i * 50,
                )
            )
        # Add a volume outlier
        candles.append(
            Candle(
                symbol="XAU/USD",
                timeframe="1h",
                timestamp=base + timedelta(hours=10),
                open=2000.0,
                high=2010.0,
                low=1995.0,
                close=2005.0,
                volume=100000.0,
            )
        )
        detector = OutlierDetector()
        outliers = detector.detect_volume_outliers(candles)
        assert len(outliers) == 1

    def test_full_validation(self, sample_candles):
        validator = DatasetValidator()
        report = validator.validate(sample_candles, "1h")
        assert report.total_records == 10
        assert report.valid_records == 10
        assert report.invalid_records == 0
        assert report.gaps_found == 0
        assert report.duplicates_found == 0
        assert report.quality_score > 0.9


# =============================================================================
# Test: Repository
# =============================================================================


class TestDatasetRepository:
    def test_save_and_get(self, sample_dataset):
        repo = DatasetRepository()
        repo.save(sample_dataset)
        retrieved = repo.get(sample_dataset.id)
        assert retrieved is not None
        assert retrieved.id == sample_dataset.id

    def test_find_by_symbol(self, sample_dataset):
        repo = DatasetRepository()
        repo.save(sample_dataset)
        results = repo.find_by_symbol("XAU/USD")
        assert len(results) == 1

    def test_find_by_timeframe(self, sample_dataset):
        repo = DatasetRepository()
        repo.save(sample_dataset)
        results = repo.find_by_timeframe("1h")
        assert len(results) == 1

    def test_find_by_symbol_and_timeframe(self, sample_dataset):
        repo = DatasetRepository()
        repo.save(sample_dataset)
        result = repo.find_by_symbol_and_timeframe("XAU/USD", "1h")
        assert result is not None

    def test_delete(self, sample_dataset):
        repo = DatasetRepository()
        repo.save(sample_dataset)
        assert repo.delete(sample_dataset.id) is True
        assert repo.get(sample_dataset.id) is None

    def test_metadata(self, sample_dataset):
        repo = DatasetRepository()
        repo.save(sample_dataset)
        meta = repo.get_metadata(sample_dataset.id)
        assert meta is not None
        assert meta.symbol == "XAU/USD"
        assert meta.record_count == 10

    def test_get_all_metadata(self, sample_dataset):
        repo = DatasetRepository()
        repo.save(sample_dataset)
        all_meta = repo.get_all_metadata()
        assert len(all_meta) == 1


class TestSqliteDatasetRepository:
    @pytest.fixture
    def db_path(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        yield path
        if os.path.exists(path):
            os.unlink(path)

    def test_save_and_get(self, sample_dataset, db_path):
        repo = SqliteDatasetRepository(db_path)
        repo.save(sample_dataset)
        retrieved = repo.get(sample_dataset.id)
        assert retrieved is not None
        assert retrieved.symbol == "XAU/USD"

    def test_find_by_symbol(self, sample_dataset, db_path):
        repo = SqliteDatasetRepository(db_path)
        repo.save(sample_dataset)
        results = repo.find_by_symbol("XAU/USD")
        assert len(results) >= 1

    def test_delete(self, sample_dataset, db_path):
        repo = SqliteDatasetRepository(db_path)
        repo.save(sample_dataset)
        assert repo.delete(sample_dataset.id) is True


# =============================================================================
# Test: HistoricalIterator
# =============================================================================


class TestHistoricalIterator:
    def test_iterate_all(self, sample_dataset):
        iterator = HistoricalIterator(sample_dataset)
        records = list(iterator)
        assert len(records) == 10

    def test_iterate_time_range(self, sample_candles):
        ds = HistoricalDataset(symbol="XAU/USD", timeframe="1h", records=sample_candles)
        ds.mark_ready()
        start = datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 15, 0, 0, tzinfo=timezone.utc)
        iterator = HistoricalIterator(ds, start_time=start, end_time=end)
        records = list(iterator)
        assert len(records) == 5  # Hours 11-15

    def test_take(self, sample_dataset):
        iterator = HistoricalIterator(sample_dataset)
        taken = iterator.take(3)
        assert len(taken) == 3

    def test_skip(self, sample_dataset):
        iterator = HistoricalIterator(sample_dataset)
        skipped = iterator.skip(3)
        assert skipped == 3
        remaining = list(iterator)
        assert len(remaining) == 7

    def test_windows(self, sample_dataset):
        iterator = HistoricalIterator(sample_dataset)
        windows = list(iterator.windows(window_size=3, step=2))
        assert len(windows) >= 4

    def test_reverse(self, sample_dataset):
        iterator = HistoricalIterator(sample_dataset, reverse=True)
        records = list(iterator)
        assert len(records) == 10
        # First record should be chronologically last
        assert records[0].timestamp > records[-1].timestamp

    def test_progress(self, sample_dataset):
        iterator = HistoricalIterator(sample_dataset)
        assert iterator.progress == 0.0
        next(iterator)
        assert iterator.progress > 0.0
        list(iterator)
        assert iterator.progress == 1.0


# =============================================================================
# Test: RangeQuery
# =============================================================================


class TestRangeQuery:
    def test_range_query(self, sample_dataset):
        query = RangeQuery(
            symbol="XAU/USD",
            timeframe="1h",
            start_time="2024-01-01T11:00:00+00:00",
            end_time="2024-01-01T15:00:00+00:00",
        )
        results = query.execute(sample_dataset)
        assert len(results) == 5

    def test_range_query_limit(self, sample_dataset):
        query = RangeQuery(
            symbol="XAU/USD",
            timeframe="1h",
            limit=3,
        )
        results = query.execute(sample_dataset)
        assert len(results) == 3

    def test_range_query_offset(self, sample_dataset):
        query = RangeQuery(
            symbol="XAU/USD",
            timeframe="1h",
            offset=5,
        )
        results = query.execute(sample_dataset)
        assert len(results) == 5

    def test_range_query_desc(self, sample_dataset):
        query = RangeQuery(
            symbol="XAU/USD",
            timeframe="1h",
            sort_order="desc",
        )
        results = query.execute(sample_dataset)
        assert len(results) == 10
        assert results[0].timestamp > results[-1].timestamp

    def test_range_query_wrong_symbol(self, sample_dataset):
        query = RangeQuery(symbol="EUR/USD", timeframe="1h")
        results = query.execute(sample_dataset)
        assert len(results) == 0

    def test_range_query_serialization(self):
        query = RangeQuery(
            symbol="XAU/USD",
            timeframe="1h",
            start_time="2024-01-01T00:00:00+00:00",
            end_time="2024-01-02T00:00:00+00:00",
            limit=100,
        )
        data = query.to_dict()
        q2 = RangeQuery.from_dict(data)
        assert q2.symbol == query.symbol
        assert q2.limit == query.limit


# =============================================================================
# Test: MultiSymbolQuery
# =============================================================================


class TestMultiSymbolQuery:
    def test_multi_symbol_query(self, sample_candles):
        ds1 = HistoricalDataset(symbol="XAU/USD", timeframe="1h", records=sample_candles)
        ds1.mark_ready()
        ds2 = HistoricalDataset(symbol="XAG/USD", timeframe="1h", records=sample_candles)
        ds2.mark_ready()

        datasets = {"XAU/USD": ds1, "XAG/USD": ds2}
        query = MultiSymbolQuery(symbols=["XAU/USD", "XAG/USD"], timeframe="1h")
        results = query.execute(datasets)
        assert "XAU/USD" in results
        assert "XAG/USD" in results
        assert len(results["XAU/USD"]) == 10

    def test_multi_symbol_serialization(self):
        query = MultiSymbolQuery(
            symbols=["XAU/USD", "XAG/USD"],
            timeframe="1h",
            start_time="2024-01-01T00:00:00+00:00",
        )
        data = query.to_dict()
        q2 = MultiSymbolQuery.from_dict(data)
        assert q2.symbols == query.symbols
        assert q2.timeframe == query.timeframe


# =============================================================================
# Test: Timezone
# =============================================================================


class TestTimezone:
    def test_utc_preserved(self):
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = normalize_timestamp(dt, "UTC")
        assert result == dt
        assert result.tzinfo is not None

    def test_est_to_utc(self):
        dt = datetime(2024, 1, 1, 12, 0, 0)
        result = normalize_timestamp(dt, "EST")
        assert result.hour == 17  # EST = UTC-5, so 12 EST = 17 UTC

    def test_convert_timezone(self):
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = convert_timezone(dt, "EST")
        assert result.hour == 7  # UTC-5

    def test_format_iso(self):
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        formatted = format_iso(dt)
        assert formatted.endswith("Z")

    def test_parse_iso(self):
        value = "2024-01-01T12:00:00Z"
        dt = parse_iso(value)
        assert dt.hour == 12
        assert dt.tzinfo is not None


# =============================================================================
# Test: Hashing
# =============================================================================


class TestHashing:
    def test_compute_dataset_hash(self, sample_dataset):
        h = compute_dataset_hash(sample_dataset)
        assert len(h) == 64
        assert h == sample_dataset.dataset_hash

    def test_verify_integrity(self, sample_dataset):
        assert verify_dataset_integrity(sample_dataset) is True

    def test_compute_candle_hash(self, candle):
        h = compute_candle_hash(candle)
        assert len(h) == 64

    def test_compute_record_hash(self, candle):
        h = compute_record_hash(candle)
        assert len(h) == 64

    def test_compute_range_hash(self, sample_candles):
        h = compute_range_hash(sample_candles[:3])
        assert len(h) == 64


# =============================================================================
# Test: Versioning
# =============================================================================


class TestDatasetVersioning:
    def test_create_version(self):
        version = DatasetVersion(
            dataset_id="test-dataset",
            version="1.0.0",
            record_count=100,
            change_description="Initial version",
        )
        assert version.version == "1.0.0"
        assert version.record_count == 100
        assert version.is_current is True

    def test_version_serialization_roundtrip(self):
        version = DatasetVersion(
            dataset_id="test-dataset",
            version="1.0.0",
            previous_version="",
            dataset_hash="abc123",
            record_count=100,
            change_description="Initial version",
            change_reason="First load",
            author="system",
        )
        data = version.to_dict()
        v2 = DatasetVersion.from_dict(data)
        assert v2.version == version.version
        assert v2.record_count == version.record_count

    def test_bump_version_patch(self):
        assert bump_dataset_version("1.0.0", "patch") == "1.0.1"
        assert bump_dataset_version("1.2.3", "patch") == "1.2.4"

    def test_bump_version_minor(self):
        assert bump_dataset_version("1.0.0", "minor") == "1.1.0"
        assert bump_dataset_version("2.5.0", "minor") == "2.6.0"

    def test_bump_version_major(self):
        assert bump_dataset_version("1.0.0", "major") == "2.0.0"
        assert bump_dataset_version("3.2.1", "major") == "4.0.0"


# =============================================================================
# Test: Contracts
# =============================================================================


class TestTimeframe:
    def test_timeframe_from_string(self):
        assert Timeframe.from_string("1h") == Timeframe.H1
        assert Timeframe.from_string("1d") == Timeframe.D1
        assert Timeframe.from_string("1w") == Timeframe.W1
        assert Timeframe.from_string("tick") == Timeframe.TICK

    def test_timeframe_to_seconds(self):
        assert Timeframe.M1.to_seconds() == 60
        assert Timeframe.H1.to_seconds() == 3600
        assert Timeframe.D1.to_seconds() == 86400

    def test_invalid_timeframe(self):
        with pytest.raises(ValueError):
            Timeframe.from_string("invalid")


class TestValidationReport:
    def test_quality_score_perfect(self):
        report = ValidationReport(total_records=100, valid_records=100)
        assert report.quality_score == 1.0

    def test_quality_score_with_gaps(self):
        report = ValidationReport(
            total_records=100,
            valid_records=90,
            gaps_found=5,
        )
        assert report.quality_score < 1.0

    def test_quality_score_empty(self):
        report = ValidationReport()
        assert report.quality_score == 0.0

    def test_serialization_roundtrip(self):
        report = ValidationReport(
            total_records=100,
            valid_records=95,
            invalid_records=5,
            gaps_found=2,
            duplicates_found=1,
            errors=["Error 1"],
            warnings=["Warning 1"],
        )
        data = report.to_dict()
        r2 = ValidationReport.from_dict(data)
        assert r2.total_records == report.total_records
        assert r2.valid_records == report.valid_records
        assert r2.quality_score == report.quality_score


# =============================================================================
# Test: CandleField and LoaderConfig
# =============================================================================


class TestLoaderConfig:
    def test_default_config(self):
        config = LoaderConfig()
        assert config.date_format == "%Y-%m-%d %H:%M:%S"
        assert config.delimiter == ","
        assert config.batch_size == 10000
        assert config.normalize_timezone is True

    def test_config_serialization_roundtrip(self):
        config = LoaderConfig(
            timezone="America/New_York",
            batch_size=5000,
            skip_errors=True,
            field_mapping=CandleField(timestamp="date", open="o", high="h", low="l", close="c"),
        )
        data = config.to_dict()
        config2 = LoaderConfig.from_dict(data)
        assert config2.timezone == config.timezone
        assert config2.batch_size == config.batch_size
        assert config2.field_mapping is not None
        assert config2.field_mapping.timestamp == "date"


# =============================================================================
# Test: DataQuality enum
# =============================================================================


class TestDataQuality:
    def test_quality_values(self):
        assert DataQuality.RAW.value == "Raw"
        assert DataQuality.CLEANED.value == "Cleaned"
        assert DataQuality.VALIDATED.value == "Validated"
        assert DataQuality.CERTIFIED.value == "Certified"


class TestDatasetStatus:
    def test_status_values(self):
        assert DatasetStatus.PENDING.value == "Pending"
        assert DatasetStatus.READY.value == "Ready"
        assert DatasetStatus.VALIDATED.value == "Validated"
        assert DatasetStatus.FAILED.value == "Failed"

def test_historical_dataset_deserialization_fails_on_corrupt_record(sample_dataset) -> None:
    data = sample_dataset.to_dict()
    data["records"][0]["timestamp"] = "not-a-timestamp"

    with pytest.raises(ValueError, match="failed candle deserialization"):
        HistoricalDataset.from_dict(data)


def test_historical_dataset_deserialization_rejects_record_count_mismatch(sample_dataset) -> None:
    data = sample_dataset.to_dict()
    data["record_count"] = data["record_count"] + 1

    with pytest.raises(ValueError, match="record_count"):
        HistoricalDataset.from_dict(data)


def test_historical_dataset_deserialization_rejects_content_hash_tampering(sample_dataset) -> None:
    data = sample_dataset.to_dict()
    data["dataset_content_hash"] = "f" * 64

    with pytest.raises(ValueError, match="dataset_content_hash"):
        HistoricalDataset.from_dict(data)
