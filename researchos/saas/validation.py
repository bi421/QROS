"""SaaS trust contract for immutable Result -> Validation lineage.

This module does not execute scientific validation. It records the identity of
an already-computed validation result and binds it to the canonical research
run/result lineage so a later API or worker cannot silently validate a
 different run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Any
from uuid import UUID
import hashlib
import json

from researchos.research_core.contracts import _validate_sha256


VALIDATION_CONTRACT_VERSION = "1.0.0"


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


@dataclass(frozen=True)
class ResearchValidationRecord:
    """Immutable SaaS identity for one precomputed validation result."""

    id: UUID
    workspace_id: UUID
    research_run_id: UUID
    result_manifest_sha256: str
    claim_id: str | None
    plan_hash: str | None
    validation_sha256: str
    status: str
    metrics: Mapping[str, float]
    contract_version: str = VALIDATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "result_manifest_sha256", _validate_sha256(self.result_manifest_sha256, "result_manifest_sha256"))
        object.__setattr__(self, "validation_sha256", _validate_sha256(self.validation_sha256, "validation_sha256"))
        if (self.claim_id is None) != (self.plan_hash is None):
            raise ValueError("claim_id and plan_hash must be provided together")
        if self.plan_hash is not None:
            object.__setattr__(self, "plan_hash", _validate_sha256(self.plan_hash, "plan_hash"))
        if not self.status.strip():
            raise ValueError("validation status must not be empty")
        object.__setattr__(self, "metrics", dict(self.metrics))
        if self.contract_version != VALIDATION_CONTRACT_VERSION:
            raise ValueError("unsupported validation contract version")

    @staticmethod
    def compute_validation_sha256(payload: Mapping[str, Any]) -> str:
        """Hash the canonical scientific validation payload supplied by the validator."""
        return hashlib.sha256(_canonical_json(dict(payload))).hexdigest()

    @staticmethod
    def canonical_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
        """Return a deterministic copy suitable for persistence/audit."""
        return json.loads(_canonical_json(dict(payload)))


__all__ = ["ResearchValidationRecord", "VALIDATION_CONTRACT_VERSION"]
