"""Idempotent persistence boundary for canonical DecisionArtifact objects."""
from __future__ import annotations
from typing import Protocol
from researchos.decision_engine.artifact import DecisionArtifact

class DecisionArtifactStore(Protocol):
    def put(self,artifact:DecisionArtifact)->DecisionArtifact: ...
    def get(self,artifact_hash:str)->DecisionArtifact|None: ...

class InMemoryDecisionArtifactStore:
    """Reference implementation; production storage can implement the same contract."""
    def __init__(self)->None:
        self._by_hash:dict[str,DecisionArtifact]={}

    def put(self,artifact:DecisionArtifact)->DecisionArtifact:
        if not artifact.verify():
            raise ValueError("cannot persist invalid decision artifact")
        existing=self._by_hash.get(artifact.artifact_hash)
        if existing is not None:
            if existing.to_dict()!=artifact.to_dict():
                raise ValueError("artifact hash collision with different content")
            return existing
        self._by_hash[artifact.artifact_hash]=artifact
        return artifact

    def get(self,artifact_hash:str)->DecisionArtifact|None:
        return self._by_hash.get(artifact_hash)

    def __len__(self)->int:
        return len(self._by_hash)
