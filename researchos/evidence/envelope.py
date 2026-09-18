"""EvidenceEnvelope — immutable, deterministic evidence graph artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

ARTIFACT_TYPES: tuple[str, ...] = (
    "Dataset",
    "Feature",
    "Experiment",
    "Run",
    "Result",
    "Validation",
    "Finding",
    "Model",
)
ARTIFACT_TYPES_TUPLE = ARTIFACT_TYPES
LINEAGE_RELATIONS: tuple[str, ...] = (
    "feeds",
    "executes",
    "produces",
    "validates",
    "derives",
    "trains",
    "contradicts",
    "replicates",
)
HASH_SCHEME_VERSION = "2"


def _validate_payload(payload: Any) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if not isinstance(key, str):
                raise TypeError(f"payload dict keys must be str, got {type(key).__name__}")
            _validate_payload(value)
        return
    if isinstance(payload, list):
        for value in payload:
            _validate_payload(value)
        return
    if isinstance(payload, (str, int, float, bool)) or payload is None:
        return
    raise TypeError(
        f"payload value {payload!r} of type {type(payload).__name__} is not a deterministic JSON-compatible primitive"
    )


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _sha256(content: Any) -> str:
    return hashlib.sha256(_canonical_json(content).encode("utf-8")).hexdigest()


def compute_artifact_hash(artifact_type: str, version: str, payload: Any) -> str:
    _validate_payload(payload)
    return _sha256(
        {
            "scheme": HASH_SCHEME_VERSION,
            "artifact_type": artifact_type,
            "version": version,
            "payload": payload,
        }
    )


def compute_lineage_hash(
    artifact_type: str,
    version: str,
    payload: Any,
    parent_hashes: Sequence[str],
) -> str:
    _validate_payload(payload)
    return _sha256(
        {
            "scheme": HASH_SCHEME_VERSION,
            "artifact_type": artifact_type,
            "version": version,
            "payload": payload,
            "parent_hashes": sorted(parent_hashes),
        }
    )


@dataclass(frozen=True)
class EvidenceEnvelope:
    artifact_type: str
    artifact_hash: str
    payload: Any = field(default_factory=dict)
    version: str = ""
    created_at: str = ""
    parent_hashes: tuple[str, ...] = field(default_factory=tuple)
    lineage_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "parent_hashes", tuple(sorted(self.parent_hashes)))
        if self.artifact_type not in ARTIFACT_TYPES:
            raise ValueError(
                f"Unknown artifact_type '{self.artifact_type}'. Expected one of {ARTIFACT_TYPES}."
            )
        if not self.artifact_hash:
            raise ValueError("artifact_hash is required")
        _validate_payload(self.payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "artifact_hash": self.artifact_hash,
            "version": self.version,
            "created_at": self.created_at,
            "payload": self.payload,
            "parent_hashes": list(self.parent_hashes),
            "lineage_hash": self.lineage_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceEnvelope":
        return cls(
            artifact_type=str(data["artifact_type"]),
            artifact_hash=str(data["artifact_hash"]),
            version=str(data.get("version", "")),
            created_at=str(data.get("created_at", "")),
            payload=data.get("payload", {}),
            parent_hashes=tuple(data.get("parent_hashes", [])),
            lineage_hash=str(data.get("lineage_hash", "")),
        )

    def verify(self) -> bool:
        if not self.lineage_hash:
            return True
        return self.lineage_hash == compute_lineage_hash(
            self.artifact_type, self.version, self.payload, self.parent_hashes
        )

    def legacy_verify(self) -> bool:
        if not self.lineage_hash:
            return True
        return self.lineage_hash == _sha256(
            {"payload": self.payload, "parent_hashes": sorted(self.parent_hashes)}
        )


def build_envelope(
    artifact_type: str,
    payload: Any,
    version: str = "",
    created_at: str = "",
    parent_hashes: Sequence[str] | None = None,
    artifact_hash: str | None = None,
) -> EvidenceEnvelope:
    _validate_payload(payload)
    if artifact_hash is None:
        artifact_hash = compute_artifact_hash(artifact_type, version, payload)
    parents = tuple(parent_hashes or ())
    return EvidenceEnvelope(
        artifact_type=artifact_type,
        artifact_hash=artifact_hash,
        payload=payload,
        version=version,
        created_at=created_at,
        parent_hashes=parents,
        lineage_hash=compute_lineage_hash(artifact_type, version, payload, parents),
    )


__all__ = [
    "ARTIFACT_TYPES",
    "ARTIFACT_TYPES_TUPLE",
    "HASH_SCHEME_VERSION",
    "LINEAGE_RELATIONS",
    "EvidenceEnvelope",
    "build_envelope",
    "compute_artifact_hash",
    "compute_lineage_hash",
]
