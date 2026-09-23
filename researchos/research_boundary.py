"""API-first boundary for deterministic research runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from researchos.data_engine.boundary import ValidatedDatasetRef
from researchos.research_identity import DatasetIdentity

RESEARCH_BOUNDARY_SCHEMA_VERSION = "research-boundary.v1"


@dataclass(frozen=True)
class ResearchInput:
    """Explicit research input contract."""

    schema_version: str
    research_id: str
    question: str
    methodology_version: str
    dataset: ValidatedDatasetRef

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_BOUNDARY_SCHEMA_VERSION:
            raise ValueError("unsupported research boundary schema version")
        if not self.research_id or not self.question:
            raise ValueError("research_id and question are required")
        if not self.methodology_version:
            raise ValueError("methodology_version is required")
        if not self.dataset.is_valid:
            raise ValueError("research input requires a valid validated-dataset reference")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "research_id": self.research_id,
            "question": self.question,
            "methodology_version": self.methodology_version,
            "dataset": self.dataset.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ResearchInput:
        return cls(
            schema_version=str(data["schema_version"]),
            research_id=str(data["research_id"]),
            question=str(data["question"]),
            methodology_version=str(data["methodology_version"]),
            dataset=ValidatedDatasetRef.from_dict(cast(dict[str, object], data["dataset"])),
        )


@dataclass(frozen=True)
class ResearchEvidenceLink:
    """Immutable lineage from research execution to its evidence output."""

    schema_version: str
    research_id: str
    dataset_id: str
    dataset_content_hash: str
    dataset_hash: str
    methodology_version: str
    execution_hash: str
    evidence_collection_id: str
    assessment_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_BOUNDARY_SCHEMA_VERSION:
            raise ValueError("unsupported research boundary schema version")
        for name, value in (
            ("research_id", self.research_id),
            ("dataset_id", self.dataset_id),
            ("dataset_content_hash", self.dataset_content_hash),
            ("dataset_hash", self.dataset_hash),
            ("methodology_version", self.methodology_version),
            ("execution_hash", self.execution_hash),
            ("evidence_collection_id", self.evidence_collection_id),
            ("assessment_hash", self.assessment_hash),
        ):
            if not value:
                raise ValueError(f"{name} is required")

    @property
    def dataset_identity(self) -> DatasetIdentity:
        return DatasetIdentity(
            dataset_id=self.dataset_id,
            dataset_content_hash=self.dataset_content_hash,
            dataset_hash=self.dataset_hash,
        )

    def assert_dataset_identity(self, reference: ValidatedDatasetRef) -> None:
        """Reject an evidence link detached from the validated input dataset."""
        self.dataset_identity.assert_matches(
            dataset_id=reference.dataset_id,
            dataset_content_hash=reference.dataset_content_hash,
            dataset_hash=reference.dataset_hash,
        )

    @classmethod
    def from_research_input(
        cls,
        research_input: ResearchInput,
        *,
        execution_hash: str,
        evidence_collection_id: str,
        assessment_hash: str,
    ) -> ResearchEvidenceLink:
        """Construct a link directly from the validated research input."""
        dataset = research_input.dataset
        return cls(
            schema_version=RESEARCH_BOUNDARY_SCHEMA_VERSION,
            research_id=research_input.research_id,
            dataset_id=dataset.dataset_id,
            dataset_content_hash=dataset.dataset_content_hash,
            dataset_hash=dataset.dataset_hash,
            methodology_version=research_input.methodology_version,
            execution_hash=execution_hash,
            evidence_collection_id=evidence_collection_id,
            assessment_hash=assessment_hash,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "research_id": self.research_id,
            "dataset_id": self.dataset_id,
            "dataset_content_hash": self.dataset_content_hash,
            "dataset_hash": self.dataset_hash,
            "methodology_version": self.methodology_version,
            "execution_hash": self.execution_hash,
            "evidence_collection_id": self.evidence_collection_id,
            "assessment_hash": self.assessment_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ResearchEvidenceLink:
        return cls(
            schema_version=str(data["schema_version"]),
            research_id=str(data["research_id"]),
            dataset_id=str(data["dataset_id"]),
            dataset_content_hash=str(data["dataset_content_hash"]),
            dataset_hash=str(data["dataset_hash"]),
            methodology_version=str(data["methodology_version"]),
            execution_hash=str(data["execution_hash"]),
            evidence_collection_id=str(data["evidence_collection_id"]),
            assessment_hash=str(data["assessment_hash"]),
        )
