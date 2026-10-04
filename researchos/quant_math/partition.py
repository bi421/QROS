from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

PARTITION_VERSION = "PROBABILITY_PARTITION_V1"
PROBABILITY_TOLERANCE = 1e-9


@dataclass(frozen=True)
class ProbabilityPartition:
    """Ordered, auditable probabilities over mutually-exclusive states."""

    partition_id: str
    hypotheses: tuple[str, ...]
    prior_probabilities: tuple[float, ...]
    partition_version: str = PARTITION_VERSION

    def __post_init__(self) -> None:
        if not self.partition_id.strip():
            raise ValueError("partition_id is required")
        if self.partition_version != PARTITION_VERSION:
            raise ValueError(f"unsupported partition_version: {self.partition_version}")
        if not self.hypotheses:
            raise ValueError("at least one hypothesis is required")
        if len(self.hypotheses) != len(self.prior_probabilities):
            raise ValueError("hypotheses and prior_probabilities must have equal length")
        if any(not h.strip() for h in self.hypotheses):
            raise ValueError("hypothesis names must be non-empty")
        if len(set(self.hypotheses)) != len(self.hypotheses):
            raise ValueError("hypotheses must be unique")
        for probability in self.prior_probabilities:
            if not isfinite(probability) or not 0.0 <= probability <= 1.0:
                raise ValueError("prior probabilities must be finite and within [0, 1]")
        if abs(sum(self.prior_probabilities) - 1.0) > PROBABILITY_TOLERANCE:
            raise ValueError("prior probabilities must sum to 1")

    @classmethod
    def from_sequences(
        cls,
        partition_id: str,
        hypotheses: Sequence[str],
        prior_probabilities: Sequence[float],
    ) -> "ProbabilityPartition":
        return cls(
            partition_id=partition_id,
            hypotheses=tuple(hypotheses),
            prior_probabilities=tuple(float(value) for value in prior_probabilities),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "partition_id": self.partition_id,
            "hypotheses": list(self.hypotheses),
            "prior_probabilities": list(self.prior_probabilities),
            "partition_version": self.partition_version,
        }
