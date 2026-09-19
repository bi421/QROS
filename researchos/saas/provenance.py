"""Deterministic SaaS provenance records for scientific run outputs."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from researchos.research_core.contracts import ResearchArtifact, ResearchResult, _validate_sha256


@dataclass(frozen=True)
class ResearchRunResultRecord:
    workspace_id: UUID
    research_run_id: UUID
    source_dataset_sha256: str
    status: str
    manifest_sha256: str
    artifacts: tuple[ResearchArtifact, ...]
    failures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_dataset_sha256",
            _validate_sha256(self.source_dataset_sha256, "source_dataset_sha256"),
        )
        object.__setattr__(
            self,
            "manifest_sha256",
            _validate_sha256(self.manifest_sha256, "manifest_sha256"),
        )
        if self.status not in {"SUCCEEDED", "FAILED"}:
            raise ValueError("status must be SUCCEEDED or FAILED")


def artifact_manifest_payload(artifacts: tuple[ResearchArtifact, ...]) -> dict[str, object]:
    """Return the canonical, order-independent identity of research artifacts."""
    identities = [
        {
            "artifact_id": artifact.artifact_id,
            "kind": artifact.kind,
            "content_sha256": artifact.content_sha256,
        }
        for artifact in sorted(
            artifacts,
            key=lambda item: (item.artifact_id, item.kind, item.content_sha256),
        )
    ]
    if len({item["artifact_id"] for item in identities}) != len(identities):
        raise ValueError("artifact_id must be unique within a manifest")
    return {"schema": "research-artifact-manifest.v1", "artifacts": identities}


def artifact_manifest_sha256(artifacts: tuple[ResearchArtifact, ...]) -> str:
    """Hash the canonical artifact manifest with deterministic JSON encoding."""
    encoded = json.dumps(
        artifact_manifest_payload(artifacts),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def manifest_payload(result: ResearchResult) -> dict[str, object]:
    return {
        "status": result.status,
        "source_dataset_sha256": result.source_dataset_sha256,
        "artifacts": [
            {
                "artifact_id": artifact.artifact_id,
                "kind": artifact.kind,
                "content_sha256": artifact.content_sha256,
            }
            for artifact in sorted(
                result.artifacts,
                key=lambda item: (item.artifact_id, item.kind, item.content_sha256),
            )
        ],
        "failures": list(result.failures),
    }


def manifest_sha256(result: ResearchResult) -> str:
    encoded = json.dumps(
        manifest_payload(result),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_result_record(
    workspace_id: UUID,
    research_run_id: UUID,
    result: ResearchResult,
) -> ResearchRunResultRecord:
    return ResearchRunResultRecord(
        workspace_id=workspace_id,
        research_run_id=research_run_id,
        source_dataset_sha256=result.source_dataset_sha256,
        status=result.status,
        manifest_sha256=manifest_sha256(result),
        artifacts=result.artifacts,
        failures=result.failures,
    )


__all__ = [
    "ResearchRunResultRecord",
    "artifact_manifest_payload",
    "artifact_manifest_sha256",
    "build_result_record",
    "manifest_payload",
    "manifest_sha256",
]
