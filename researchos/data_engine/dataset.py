"""
HistoricalDataset — collection of market data for a symbol and timeframe.

Based on Article XVII: Object Model — Data Layer.

A HistoricalDataset represents a complete collection of market data
(candles, ticks, quotes, trades, or order books) for a specific symbol
and timeframe. It includes metadata, statistics, and content hashing
for integrity verification.

Guarantees:
    - Deterministic: Same data → same dataset hash
    - Auditable: Full lifecycle from Pending to Ready to Archived
    - Serializable: Supports to_dict/from_dict
    - Immutable: Data is never modified after freezing
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Union

from researchos.core.base_object import BaseObject
from researchos.core.identity import deterministic_hash, generate_id
from researchos.core.lifecycle import LifecycleStage
from researchos.data_engine.candle import Candle
from researchos.data_engine.contracts import DataQuality, DatasetStatus
from researchos.data_engine.orderbook import OrderBook
from researchos.data_engine.quote import Quote
from researchos.data_engine.tick import Tick
from researchos.data_engine.trade import Trade

DataRecord = Union[Candle, Tick, Quote, Trade, OrderBook]


def _restore_record(data_type: str, data: dict[str, Any]) -> DataRecord | None:
    """Reconstruct a typed data record from its serialized dict."""
    try:
        if data_type == "candle":
            return Candle.from_dict(data)
        if data_type == "tick":
            return Tick.from_dict(data)
        if data_type == "quote":
            return Quote.from_dict(data)
        if data_type == "trade":
            return Trade.from_dict(data)
        if data_type == "orderbook":
            return OrderBook.from_dict(data)
    except Exception:
        return None
    return None


class HistoricalDataset(BaseObject):
    """
    A complete collection of market data for a symbol and timeframe.

    Attributes:
        symbol: The trading symbol.
        timeframe: The data timeframe.
        data_type: Type of data ('candle', 'tick', 'quote', 'trade', 'orderbook').
        records: List of data records.
        source: Source identifier.
        quality: Data quality grade.
        status: Dataset lifecycle status.
        record_count: Total number of records.
        start_time: UTC timestamp of first record.
        end_time: UTC timestamp of last record.
        dataset_hash: Deterministic hash of all records.
        dataset_content_hash: Content-based identity (records only).
        version: Dataset version string.
        tags: Tags for categorisation.
    """

    def __init__(
        self,
        symbol: str,
        timeframe: str,
        data_type: str = "candle",
        records: list[DataRecord] | None = None,
        source: str = "",
        quality: str = "Raw",
        version: str = "1.0.0",
        tags: list[str] | None = None,
        ontology_tags: list[str] | None = None,
        id: str | None = None,
    ):
        if id is None:
            seed = f"HistoricalDataset|{symbol}|{timeframe}|{source}"
            id = generate_id(seed)

        super().__init__(id=id, ontology_tags=ontology_tags)

        self.symbol = symbol
        self.timeframe = timeframe
        self.data_type = data_type
        self._records: list[DataRecord] = records or []
        self.source = source
        self.quality = DataQuality(quality) if isinstance(quality, str) else quality
        self.status = DatasetStatus.PENDING
        self.version = version
        self.tags: list[str] = tags or []
        self.dataset_hash: str = ""
        self.dataset_content_hash: str = ""
        self._record_hashes: list[str] = []
        self._frozen: bool = False

        self.lifecycle.transition(
            LifecycleStage.CREATED,
            reason=f"HistoricalDataset created: {symbol} {timeframe}",
        )

    @property
    def records(self) -> list[DataRecord]:
        """Get all records in the dataset."""
        return list(self._records)

    @property
    def record_count(self) -> int:
        """Total number of records."""
        return len(self._records)

    @property
    def start_time(self) -> datetime | None:
        """Timestamp of the first record."""
        if not self._records:
            return None
        first = self._records[0]
        return first.timestamp if hasattr(first, "timestamp") else None

    @property
    def end_time(self) -> datetime | None:
        """Timestamp of the last record."""
        if not self._records:
            return None
        last = self._records[-1]
        return last.timestamp if hasattr(last, "timestamp") else None

    @property
    def duration_seconds(self) -> float:
        """Total time span covered by the dataset in seconds."""
        start = self.start_time
        end = self.end_time
        if start and end:
            return (end - start).total_seconds()
        return 0.0

    def add_record(self, record: DataRecord) -> None:
        """Add a single record to the dataset."""
        if self._frozen:
            raise ValueError("Dataset is immutable after mark_ready(); add_record() is not allowed.")
        self._records.append(record)
        self._compute_hash()

    def add_records(self, records: list[DataRecord]) -> None:
        """Add multiple records to the dataset."""
        if self._frozen:
            raise ValueError("Dataset is immutable after mark_ready(); add_records() is not allowed.")
        self._records.extend(records)
        self._compute_hash()

    def sort(self) -> None:
        """Sort records chronologically by timestamp."""
        self._records.sort(key=lambda r: r.timestamp if hasattr(r, "timestamp") else datetime.min)

    def mark_ready(self) -> None:
        """Mark the dataset as ready for use."""
        self.sort()
        self._compute_hash()
        self._frozen = True
        self.status = DatasetStatus.READY
        self.lifecycle.transition(
            LifecycleStage.ACTIVE,
            reason=f"Dataset ready: {self.record_count} records",
        )

    def mark_validated(self) -> None:
        """Mark the dataset as validated."""
        self.status = DatasetStatus.VALIDATED
        self.lifecycle.transition(
            LifecycleStage.VALIDATED,
            reason="Dataset validated",
        )

    def mark_failed(self, reason: str = "") -> None:
        """Mark the dataset as failed."""
        self.status = DatasetStatus.FAILED
        self.lifecycle.transition(
            LifecycleStage.INVALIDATED,
            reason=f"Dataset failed: {reason}" if reason else "Dataset failed",
        )

    def _compute_hash(self) -> None:
        """Compute deterministic hash of all records."""
        record_hashes = []
        for record in self._records:
            h = record.hash if hasattr(record, "hash") else str(id(record))
            record_hashes.append(h)

        self._record_hashes = record_hashes
        content = {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "data_type": self.data_type,
            "source": self.source,
            "record_count": len(self._records),
            "record_hashes": sorted(record_hashes),
            "version": self.version,
            "tags": sorted(self.tags),
            "ontology_tags": sorted(self.ontology_tags),
        }
        self.dataset_hash = deterministic_hash(content)

        # Content-based identity: derived ONLY from the records themselves.
        # Two datasets with different candle records MUST produce different
        # content hashes, even if symbol/timeframe/source are identical.
        self.dataset_content_hash = deterministic_hash({"record_hashes": sorted(record_hashes)})

    def _to_hashable_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "data_type": self.data_type,
            "source": self.source,
            "quality": self.quality.value,
            "status": self.status.value,
            "record_count": len(self._records),
            "record_hashes": self._record_hashes,
            "dataset_hash": self.dataset_hash,
            "dataset_content_hash": self.dataset_content_hash,
            "version": self.version,
            "tags": sorted(self.tags),
            "ontology_tags": sorted(self.ontology_tags),
        }

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update(
            {
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "data_type": self.data_type,
                "source": self.source,
                "quality": self.quality.value,
                "status": self.status.value,
                "record_count": len(self._records),
                "start_time": self.start_time.isoformat() if self.start_time else None,
                "end_time": self.end_time.isoformat() if self.end_time else None,
                "duration_seconds": self.duration_seconds,
                "dataset_hash": self.dataset_hash,
                "dataset_content_hash": self.dataset_content_hash,
                "version": self.version,
                "tags": self.tags,
                "records": [r.to_dict() if hasattr(r, "to_dict") else str(r) for r in self._records],
            }
        )
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistoricalDataset:
        obj = super().from_dict(data)
        obj.symbol = data["symbol"]
        obj.timeframe = data["timeframe"]
        obj.data_type = data.get("data_type", "candle")
        obj.source = data.get("source", "")
        obj.quality = DataQuality(data.get("quality", "Raw"))
        obj.status = DatasetStatus(data.get("status", "Pending"))
        obj.dataset_hash = data.get("dataset_hash", "")
        obj.dataset_content_hash = data.get("dataset_content_hash", "")
        obj.version = data.get("version", "1.0.0")
        obj.tags = list(data.get("tags", []))
        obj._records = cls._deserialize_records(data.get("records", []), obj.data_type)

        # Freeze the restored dataset if it was already committed.
        obj._frozen = obj.status in (
            DatasetStatus.READY,
            DatasetStatus.VALIDATED,
            DatasetStatus.ARCHIVED,
        )

        # Recompute hashes from restored records and fail closed on any
        # serialization truncation or identity mismatch.
        obj._compute_hash()
        expected_count = data.get("record_count")
        if expected_count is not None and int(expected_count) != obj.record_count:
            raise ValueError(
                "dataset record_count does not match restored records"
            )
        expected_content_hash = data.get("dataset_content_hash")
        if expected_content_hash and expected_content_hash != obj.dataset_content_hash:
            raise ValueError(
                "dataset_content_hash does not match restored records"
            )
        expected_dataset_hash = data.get("dataset_hash")
        if expected_dataset_hash and expected_dataset_hash != obj.dataset_hash:
            raise ValueError("dataset_hash does not match restored dataset")
        return obj

    @staticmethod
    def _deserialize_records(records: list[Any], data_type: str) -> list[DataRecord]:
        """
        Reconstruct typed data records from serialized dicts.

        The dataset has a single data_type, so the record class is known
        before iterating. This restores full record fidelity on load.
        """
        record_map = {
            "candle": Candle,
            "tick": Tick,
            "quote": Quote,
            "trade": Trade,
            "orderbook": OrderBook,
        }
        record_cls = record_map.get(data_type)
        if record_cls is None:
            raise ValueError(f"unsupported dataset data_type: {data_type!r}")

        restored: list[DataRecord] = []
        for index, rec in enumerate(records):
            if not isinstance(rec, dict):
                raise ValueError(
                    f"dataset record {index} is not a serialized mapping"
                )
            try:
                restored.append(record_cls.from_dict(rec))
            except Exception as exc:
                # A persisted dataset must never silently lose a record during
                # deserialization; callers need an explicit integrity failure.
                if data_type != "candle" and "open" in rec and "close" in rec:
                    try:
                        restored.append(Candle.from_dict(rec))
                        continue
                    except Exception:
                        pass
                raise ValueError(
                    f"dataset record {index} failed {data_type} deserialization"
                ) from exc
        return restored

    def __repr__(self) -> str:
        return f"HistoricalDataset({self.symbol}, {self.timeframe}, {self.record_count} records, {self.status.value})"

    def __len__(self) -> int:
        return len(self._records)

    def __getitem__(self, index: int) -> DataRecord:
        return self._records[index]

    def __iter__(self):
        return iter(self._records)
