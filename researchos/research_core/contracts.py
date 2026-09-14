"""Contracts between the scientific core and delivery applications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol

FROZEN_XAUUSD_M1_WORKFLOW = "xauusd_m1_frozen_research_v1"


def _validate_sha256(value: str, field_name: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError(f"{field_name} must be a 64-character SHA-256 hex digest")
    return normalized


@dataclass(frozen=True)
class ResearchDataset:
    """Immutable dataset identity supplied to the scientific core.

    The core receives identity and row access, not a storage/database client.
    Delivery layers are responsible for resolving their own storage into this
    contract before execution.
    """

    dataset_id: str
    asset: str
    timeframe: str
    content_sha256: str
    rows: Iterable[Mapping[str, object]]

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise ValueError("dataset_id must not be empty")
        if not self.asset.strip():
            raise ValueError("asset must not be empty")
        if not self.timeframe.strip():
            raise ValueError("timeframe must not be empty")
        object.__setattr__(self, "content_sha256", _validate_sha256(self.content_sha256, "content_sha256"))


@dataclass(frozen=True)
class ResearchRequest:
    """A scientific execution request with no SaaS/application state."""

    dataset: ResearchDataset
    workflow_id: str = FROZEN_XAUUSD_M1_WORKFLOW

    def __post_init__(self) -> None:
        if self.workflow_id != FROZEN_XAUUSD_M1_WORKFLOW:
            raise ValueError(f"unsupported workflow_id: {self.workflow_id!r}")
        if self.dataset.asset.upper() != "XAUUSD":
            raise ValueError("the frozen MVP workflow only accepts XAUUSD")
        if self.dataset.timeframe.upper() != "M1":
            raise ValueError("the frozen MVP workflow only accepts M1")


@dataclass(frozen=True)
class ResearchArtifact:
    """Content-addressed output produced by the scientific core."""

    artifact_id: str
    kind: str
    content_sha256: str

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            raise ValueError("artifact_id must not be empty")
        if not self.kind.strip():
            raise ValueError("kind must not be empty")
        object.__setattr__(self, "content_sha256", _validate_sha256(self.content_sha256, "content_sha256"))


@dataclass(frozen=True)
class ResearchResult:
    """Scientific result envelope returned to any delivery mode."""

    status: str
    source_dataset_sha256: str
    artifacts: tuple[ResearchArtifact, ...] = ()
    failures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"SUCCEEDED", "FAILED"}:
            raise ValueError("status must be SUCCEEDED or FAILED")
        object.__setattr__(
            self,
            "source_dataset_sha256",
            _validate_sha256(self.source_dataset_sha256, "source_dataset_sha256"),
        )
        if self.status == "SUCCEEDED" and self.failures:
            raise ValueError("a successful result cannot contain failures")


class ResearchRunner(Protocol):
    """Application-neutral entry point implemented by the scientific core."""

    def run(self, request: ResearchRequest) -> ResearchResult:
        """Execute the frozen scientific workflow deterministically."""
