"""Immutable SaaS trust contract for Result -> Validation -> Finding lineage.

This layer does not infer a scientific finding. It records a caller-supplied,
already validated finding payload and binds it to the canonical validation,
result manifest, claim, and research plan lineage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID
import hashlib
import json

from researchos.research_core.contracts import _validate_sha256

FINDING_CONTRACT_VERSION = "1.0.0"
VALIDATED_STATUS = "VALIDATED"


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


@dataclass(frozen=True)
class ResearchFindingRecord:
    id: UUID
    workspace_id: UUID
    research_run_id: UUID
    validation_id: UUID
    result_manifest_sha256: str
    validation_sha256: str
    claim_id: str | None
    plan_hash: str | None
    finding_sha256: str
    status: str
    payload: Mapping[str, Any]
    contract_version: str = FINDING_CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "result_manifest_sha256", _validate_sha256(self.result_manifest_sha256, "result_manifest_sha256"))
        object.__setattr__(self, "validation_sha256", _validate_sha256(self.validation_sha256, "validation_sha256"))
        object.__setattr__(self, "finding_sha256", _validate_sha256(self.finding_sha256, "finding_sha256"))
        if (self.claim_id is None) != (self.plan_hash is None):
            raise ValueError("claim_id and plan_hash must be provided together")
        if self.plan_hash is not None:
            object.__setattr__(self, "plan_hash", _validate_sha256(self.plan_hash, "plan_hash"))
        if self.status != VALIDATED_STATUS:
            raise ValueError("research finding status must be VALIDATED")
        if self.contract_version != FINDING_CONTRACT_VERSION:
            raise ValueError("unsupported finding contract version")
        canonical = self.canonical_payload(self.payload)
        object.__setattr__(self, "payload", canonical)
        if self.compute_finding_sha256(canonical) != self.finding_sha256:
            raise ValueError("finding_sha256 does not match canonical payload")

    @staticmethod
    def canonical_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
        return json.loads(_canonical_json(dict(payload)))

    @staticmethod
    def compute_finding_sha256(payload: Mapping[str, Any]) -> str:
        return hashlib.sha256(_canonical_json(dict(payload))).hexdigest()


__all__ = ["FINDING_CONTRACT_VERSION", "VALIDATED_STATUS", "ResearchFindingRecord"]
