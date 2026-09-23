"""API-first boundary for validated datasets entering research."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from researchos.data_engine.contracts import DatasetStatus, ValidationReport
from researchos.data_engine.dataset import HistoricalDataset

DATA_BOUNDARY_SCHEMA_VERSION = "data-boundary.v1"


@dataclass(frozen=True)
class ValidatedDatasetRef:
    """Immutable reference to a validated dataset.

    The research layer receives identity and validation evidence, not a mutable
    dataset object. Raw records remain owned by the data layer.
    """

    schema_version: str
    dataset_id: str
    dataset_content_hash: str
    dataset_hash: str
    symbol: str
    timeframe: str
    data_type: str
    record_count: int
    validation_quality_score: float
    validation_errors: tuple[str, ...] = ()
    validation_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != DATA_BOUNDARY_SCHEMA_VERSION:
            raise ValueError("unsupported data boundary schema version")
        if not self.dataset_id or not self.dataset_content_hash or not self.dataset_hash:
            raise ValueError("complete dataset identity is required")
        if self.record_count < 0:
            raise ValueError("record_count must be non-negative")
        if not 0.0 <= self.validation_quality_score <= 1.0:
            raise ValueError("validation_quality_score must be in [0, 1]")

    @property
    def is_valid(self) -> bool:
        return not self.validation_errors and self.validation_quality_score > 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "dataset_content_hash": self.dataset_content_hash,
            "dataset_hash": self.dataset_hash,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "data_type": self.data_type,
            "record_count": self.record_count,
            "validation_quality_score": self.validation_quality_score,
            "validation_errors": list(self.validation_errors),
            "validation_warnings": list(self.validation_warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ValidatedDatasetRef:
        return cls(
            schema_version=str(data["schema_version"]),
            dataset_id=str(data["dataset_id"]),
            dataset_content_hash=str(data["dataset_content_hash"]),
            dataset_hash=str(data["dataset_hash"]),
            symbol=str(data["symbol"]),
            timeframe=str(data["timeframe"]),
            data_type=str(data["data_type"]),
            record_count=int(cast(int, data["record_count"])),
            validation_quality_score=float(
                cast(float, data["validation_quality_score"])
            ),
            validation_errors=tuple(
                str(x) for x in cast(Iterable[object], data.get("validation_errors", []))
            ),
            validation_warnings=tuple(
                str(x)
                for x in cast(Iterable[object], data.get("validation_warnings", []))
            ),
        )


def validated_dataset_ref(
    dataset: HistoricalDataset,
    validation: ValidationReport,
) -> ValidatedDatasetRef:
    """Create the research-facing reference only after complete validation."""
    if dataset.status != DatasetStatus.VALIDATED:
        raise ValueError("dataset must have DatasetStatus.VALIDATED before crossing the boundary")
    if not dataset.dataset_content_hash or not dataset.dataset_hash:
        raise ValueError("complete dataset identity is required before crossing the boundary")
    if validation.errors:
        raise ValueError("validation errors must be empty before crossing the boundary")
    if validation.total_records != dataset.record_count:
        raise ValueError("validation record count must match dataset record count")
    if validation.quality_score <= 0.0:
        raise ValueError("validation quality score must be greater than zero")

    return ValidatedDatasetRef(
        schema_version=DATA_BOUNDARY_SCHEMA_VERSION,
        dataset_id=dataset.id,
        dataset_content_hash=dataset.dataset_content_hash,
        dataset_hash=dataset.dataset_hash,
        symbol=dataset.symbol,
        timeframe=dataset.timeframe,
        data_type=dataset.data_type,
        record_count=dataset.record_count,
        validation_quality_score=validation.quality_score,
        validation_errors=tuple(validation.errors),
        validation_warnings=tuple(validation.warnings),
    )
