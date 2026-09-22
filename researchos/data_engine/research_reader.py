"""Validated-data reader for the Research execution boundary.

This module is deliberately owned by the data layer.  Research execution
receives a :class:`ValidatedDatasetRef`; this adapter resolves that reference
to immutable primitive series without exposing ``HistoricalDataset`` in the
research execution API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from researchos.data_engine.boundary import ValidatedDatasetRef
from researchos.data_engine.candle import Candle
from researchos.data_engine.contracts import DatasetStatus
from researchos.data_engine.dataset import HistoricalDataset


@dataclass(frozen=True)
class ResearchSeries:
    """Immutable OHLCV series materialized by the data boundary."""

    close: tuple[float, ...]
    high: tuple[float, ...]
    low: tuple[float, ...]
    volume: tuple[float, ...]

    def __post_init__(self) -> None:
        lengths = {len(self.close), len(self.high), len(self.low), len(self.volume)}
        if len(lengths) != 1:
            raise ValueError("research series fields must have equal length")


class DatasetResearchReader:
    """Resolve a validated dataset reference into research-safe primitive data."""

    def __init__(self, repository: Any):
        self._repository = repository

    def resolve(self, reference: ValidatedDatasetRef) -> ResearchSeries:
        """Resolve and re-check dataset identity before data crosses the boundary."""
        dataset = self._repository.get(reference.dataset_id)
        if not isinstance(dataset, HistoricalDataset):
            raise ValueError("validated dataset reference could not be resolved")
        if dataset.status is not DatasetStatus.VALIDATED:
            raise ValueError("resolved dataset is no longer validated")
        if dataset.dataset_content_hash != reference.dataset_content_hash:
            raise ValueError("dataset content hash does not match validated reference")
        if dataset.dataset_hash != reference.dataset_hash:
            raise ValueError("dataset hash does not match validated reference")
        if dataset.data_type != "candle":
            raise ValueError("Phase 5.1 research requires candle data")

        records = dataset.records
        if not all(isinstance(record, Candle) for record in records):
            raise ValueError("validated candle dataset contains non-candle records")
        candle_records = tuple(record for record in records if isinstance(record, Candle))
        return ResearchSeries(
            close=tuple(float(record.close) for record in candle_records),
            high=tuple(float(record.high) for record in candle_records),
            low=tuple(float(record.low) for record in candle_records),
            volume=tuple(float(record.volume) for record in candle_records),
        )


__all__ = ["ResearchSeries", "DatasetResearchReader"]
