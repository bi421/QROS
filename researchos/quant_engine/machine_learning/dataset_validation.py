"""Dataset Builder — validation.

Functions that validate a ResearchDataset and raise descriptive
exceptions when the structure is invalid.
"""

from __future__ import annotations

import math

from .dataset_contracts import ResearchDataset


def validate_dataset(dataset: ResearchDataset) -> None:
    """Run the full validation suite on the dataset."""
    if not isinstance(dataset, ResearchDataset):
        raise TypeError(f"expected ResearchDataset, got {type(dataset).__name__}")
    validate_shapes(dataset)
    validate_feature_count(dataset)
    validate_no_none(dataset)
    validate_no_nan(dataset)
    validate_alignment(dataset)


def validate_shapes(dataset: ResearchDataset) -> None:
    """Ensure features, labels and sample_count agree on the row count."""
    if len(dataset.features) != dataset.sample_count:
        raise ValueError(f"features length {len(dataset.features)} != sample_count {dataset.sample_count}")
    if len(dataset.labels) != dataset.sample_count:
        raise ValueError(f"labels length {len(dataset.labels)} != sample_count {dataset.sample_count}")


def validate_feature_count(dataset: ResearchDataset) -> None:
    """Ensure every feature row has exactly feature_count columns."""
    for idx, row in enumerate(dataset.features):
        if len(row) != dataset.feature_count:
            raise ValueError(f"feature row {idx} has {len(row)} columns, expected {dataset.feature_count}")
    if len(dataset.feature_names) != dataset.feature_count:
        raise ValueError(f"feature_names length {len(dataset.feature_names)} != feature_count {dataset.feature_count}")


def validate_no_none(dataset: ResearchDataset) -> None:
    """Ensure no None values appear in features or labels."""
    for idx, row in enumerate(dataset.features):
        for col, value in enumerate(row):
            if value is None:
                raise ValueError(f"None value at feature[{idx}][{col}]")
    for idx, value in enumerate(dataset.labels):
        if value is None:
            raise ValueError(f"None label at index {idx}")


def validate_no_nan(dataset: ResearchDataset) -> None:
    """Ensure no NaN values appear in features or labels."""
    for idx, row in enumerate(dataset.features):
        for col, value in enumerate(row):
            if isinstance(value, float) and math.isnan(value):
                raise ValueError(f"NaN value at feature[{idx}][{col}]")
    for idx, value in enumerate(dataset.labels):
        if isinstance(value, float) and math.isnan(value):
            raise ValueError(f"NaN label at index {idx}")


def validate_alignment(dataset: ResearchDataset) -> None:
    """Ensure feature rows and labels are structurally aligned."""
    if len(dataset.features) != len(dataset.labels):
        raise ValueError(f"alignment violated: {len(dataset.features)} feature rows vs {len(dataset.labels)} labels")


__all__ = [
    "validate_alignment",
    "validate_dataset",
    "validate_feature_count",
    "validate_no_nan",
    "validate_no_none",
    "validate_shapes",
]
