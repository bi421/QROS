"""Deterministic, content-addressed research reproducibility manifest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

from researchos.research_core.contracts import ResearchArtifact, _validate_sha256

MANIFEST_SCHEMA_VERSION = "1"


def _hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ArtifactManifest:
    """Immutable identity of all artifacts required to reproduce a research result."""

    dataset_sha256: str
    plan_sha256: str
    artifacts: tuple[ResearchArtifact, ...] = ()
    schema_version: str = MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_sha256", _validate_sha256(self.dataset_sha256, "dataset_sha256"))
        object.__setattr__(self, "plan_sha256", _validate_sha256(self.plan_sha256, "plan_sha256"))
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise ValueError(f"unsupported manifest schema version: {self.schema_version!r}")
        if tuple(sorted(self.artifacts, key=lambda a: (a.artifact_id, a.kind, a.content_sha256))) != self.artifacts:
            raise ValueError("artifacts must be deterministically sorted")
        if len({a.artifact_id for a in self.artifacts}) != len(self.artifacts):
            raise ValueError("artifact_id values must be unique")

    @classmethod
    def build(cls, dataset_sha256: str, plan_sha256: str, artifacts: Iterable[ResearchArtifact]) -> "ArtifactManifest":
        ordered = tuple(sorted(artifacts, key=lambda a: (a.artifact_id, a.kind, a.content_sha256)))
        return cls(dataset_sha256=dataset_sha256, plan_sha256=plan_sha256, artifacts=ordered)

    @property
    def payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dataset_sha256": self.dataset_sha256,
            "plan_sha256": self.plan_sha256,
            "artifacts": [
                {"artifact_id": a.artifact_id, "kind": a.kind, "content_sha256": a.content_sha256}
                for a in self.artifacts
            ],
        }

    @property
    def manifest_sha256(self) -> str:
        return _hash(self.payload)

    def verify(self, expected_sha256: str) -> bool:
        return self.manifest_sha256 == _validate_sha256(expected_sha256, "expected_sha256")


__all__ = ["ArtifactManifest", "MANIFEST_SCHEMA_VERSION"]
