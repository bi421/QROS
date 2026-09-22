"""
Dataset hashing utilities — deterministic content hashing for market data.

Based on Article XVII: Object Model — Data Layer.

Provides deterministic content hashing for datasets, records, and
data integrity verification. Every dataset and record has a hash
that uniquely identifies its content.

Guarantees:
    - Deterministic: Same data → same hash
    - Collision-resistant: SHA-256 based
    - Verifiable: Hashes can be independently recomputed
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from researchos.core.identity import deterministic_hash
from researchos.data_engine.candle import Candle
from researchos.data_engine.dataset import HistoricalDataset


def compute_dataset_hash(dataset: HistoricalDataset) -> str:
    """
    Compute a deterministic hash for a complete dataset.

    The hash is computed from:
        - Symbol, timeframe, source
        - Record count and time range
        - All individual record hashes

    Args:
        dataset: The dataset to hash.

    Returns:
        SHA-256 hash string.
    """
    # Build record-level content
    record_content: list[str] = []
    for record in dataset._records:
        if hasattr(record, "hash"):
            record_content.append(record.hash)
        elif hasattr(record, "to_dict"):
            h = deterministic_hash(record.to_dict())
            record_content.append(h)

    content = {
        "symbol": dataset.symbol,
        "timeframe": dataset.timeframe,
        "data_type": dataset.data_type,
        "source": dataset.source,
        "record_count": len(dataset._records),
        "record_hashes": sorted(record_content),
        "version": dataset.version,
        "tags": sorted(dataset.tags),
        "ontology_tags": sorted(dataset.ontology_tags),
    }

    return deterministic_hash(content)


def compute_candle_hash(candle: Candle) -> str:
    """
    Compute a deterministic hash for a single Candle.

    Args:
        candle: The candle to hash.

    Returns:
        SHA-256 hash string.
    """
    return candle.hash


def compute_record_hash(record: Any) -> str:
    """
    Compute a deterministic hash for any record type.

    Args:
        record: Candle, Tick, Quote, or Trade object.

    Returns:
        SHA-256 hash string.
    """
    if hasattr(record, "hash"):
        value = getattr(record, "hash")
        if isinstance(value, str):
            return value
        return str(value)

    if hasattr(record, "to_dict"):
        return deterministic_hash(record.to_dict())

    return deterministic_hash(str(record))


def verify_dataset_integrity(dataset: HistoricalDataset) -> bool:
    """
    Verify that a dataset's hash matches its current content.

    Args:
        dataset: The dataset to verify.

    Returns:
        True if the dataset hash matches its content.
    """
    computed = compute_dataset_hash(dataset)
    stored = dataset.dataset_hash
    return computed == stored


def compute_range_hash(
    records: list[Any],
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> str:
    """
    Compute a hash for a subset (range) of records.

    Args:
        records: List of records to hash.
        start_time: Optional start time for the range.
        end_time: Optional end time for the range.

    Returns:
        SHA-256 hash string.
    """
    content = {
        "start_time": start_time.isoformat() if start_time else None,
        "end_time": end_time.isoformat() if end_time else None,
        "record_count": len(records),
        "record_hashes": [compute_record_hash(r) for r in records],
    }
    return deterministic_hash(content)
