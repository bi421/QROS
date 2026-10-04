"""Idempotent persistence boundary for hash-linked risk decision artifacts."""

from __future__ import annotations

from typing import Protocol

from researchos.risk.decision_artifact import RiskDecisionArtifact


class RiskDecisionArtifactStore(Protocol):
    def put(self, artifact: RiskDecisionArtifact) -> RiskDecisionArtifact: ...
    def get(self, artifact_hash: str) -> RiskDecisionArtifact | None: ...


class InMemoryRiskDecisionArtifactStore:
    """Reference store with validation, replay idempotency and collision protection."""

    def __init__(self) -> None:
        self._by_hash: dict[str, RiskDecisionArtifact] = {}

    def put(self, artifact: RiskDecisionArtifact) -> RiskDecisionArtifact:
        if not artifact.verify():
            raise ValueError("cannot persist invalid risk decision artifact")
        existing = self._by_hash.get(artifact.artifact_hash)
        if existing is not None:
            if existing.to_dict() != artifact.to_dict():
                raise ValueError(
                    "risk decision artifact hash collision with different content"
                )
            return existing
        self._by_hash[artifact.artifact_hash] = artifact
        return artifact

    def get(self, artifact_hash: str) -> RiskDecisionArtifact | None:
        return self._by_hash.get(artifact_hash)

    def __len__(self) -> int:
        return len(self._by_hash)


__all__ = ["RiskDecisionArtifactStore", "InMemoryRiskDecisionArtifactStore"]
