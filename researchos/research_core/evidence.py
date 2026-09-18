"""Immutable evidence artifacts used to substantiate governed research gates.

Evidence is provenance, not a statistical claim by itself.  Each artifact binds
an evidence identity to a dataset, analysis, partition and content hash so
downstream governance can reject unverifiable OOS/replication declarations.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from researchos.research_core.contracts import _validate_sha256


class EvidenceKind(str, Enum):
    OUT_OF_SAMPLE = "OUT_OF_SAMPLE"
    REPLICATION = "REPLICATION"


@dataclass(frozen=True)
class EvidenceArtifact:
    """Immutable provenance record for a validation or replication artifact."""

    evidence_id: str
    kind: EvidenceKind
    analysis_id: str
    dataset_id: str
    dataset_sha256: str
    partition_id: str
    population_definition: str
    sample_size: int
    content_sha256: str
    independent_of_analysis_id: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("evidence_id", self.evidence_id),
            ("analysis_id", self.analysis_id),
            ("dataset_id", self.dataset_id),
            ("partition_id", self.partition_id),
            ("population_definition", self.population_definition),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        object.__setattr__(
            self, "dataset_sha256", _validate_sha256(self.dataset_sha256, "dataset_sha256")
        )
        object.__setattr__(
            self, "content_sha256", _validate_sha256(self.content_sha256, "content_sha256")
        )
        if self.sample_size < 1:
            raise ValueError("sample_size must be >= 1")
        if self.kind is EvidenceKind.REPLICATION:
            if not self.independent_of_analysis_id:
                raise ValueError(
                    "replication evidence requires independent_of_analysis_id"
                )
            if self.independent_of_analysis_id == self.analysis_id:
                raise ValueError(
                    "replication evidence must be independent of the source analysis"
                )

    @property
    def evidence_sha256(self) -> str:
        payload = {
            "evidence_id": self.evidence_id,
            "kind": self.kind.value,
            "analysis_id": self.analysis_id,
            "dataset_id": self.dataset_id,
            "dataset_sha256": self.dataset_sha256,
            "partition_id": self.partition_id,
            "population_definition": self.population_definition,
            "sample_size": self.sample_size,
            "content_sha256": self.content_sha256,
            "independent_of_analysis_id": self.independent_of_analysis_id,
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


__all__ = ["EvidenceArtifact", "EvidenceKind"]
