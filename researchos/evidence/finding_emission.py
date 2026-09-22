"""Research finding evidence emission.

Bridges the existing ``market_memory.EvidenceRecord`` contract into the
append-only evidence graph as a deterministic ``Finding`` artifact.

A finding may only be certified from an existing Validation artifact and must
itself be marked ``VALIDATED``.  This keeps the durable-knowledge boundary
explicit: exploratory or rejected observations cannot be promoted by this API.

    Experiment -> Run -> Result -> Validation -> Finding

This module does not compute findings; it only records an already-produced
finding together with its provenance.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from researchos.evidence.envelope import EvidenceEnvelope, build_envelope
from researchos.evidence.repository import EvidenceRepository

FINDING_ARTIFACT_TYPE = "Finding"
FINDING_EVIDENCE_VERSION = "1.0.0"
VALIDATION_TO_FINDING_RELATION = "derives"
VALIDATION_ARTIFACT_TYPE = "Validation"
VALIDATED_STATUS = "VALIDATED"


def _primitives(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _primitives(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_primitives(item) for item in value]
    return value


def finding_payload(finding: Any) -> dict[str, Any]:
    """Project an EvidenceRecord into a deterministic payload."""
    data = finding.to_dict()
    data.pop("created_at", None)
    projected = _primitives(data)
    if not isinstance(projected, dict):
        raise TypeError("finding payload must project to a dictionary")
    return projected


def finding_hash(finding: Any) -> str:
    """Return the deterministic content hash of a research finding."""
    from researchos.core.identity import deterministic_hash

    return deterministic_hash(finding_payload(finding))


def build_finding_envelope(
    finding: Any,
    *,
    validation_hash: str,
    version: str = FINDING_EVIDENCE_VERSION,
    created_at: str = "",
) -> EvidenceEnvelope:
    """Build a Finding envelope whose parent is the certified Validation."""
    if not validation_hash:
        raise ValueError("validation_hash is required to certify a finding")
    payload = finding_payload(finding)
    return build_envelope(
        artifact_type=FINDING_ARTIFACT_TYPE,
        payload=payload,
        version=version,
        created_at=created_at,
        parent_hashes=(validation_hash,),
    )


def emit_finding(
    envelope: EvidenceEnvelope,
    repository: EvidenceRepository | None = None,
) -> EvidenceEnvelope:
    """Append a validated Finding envelope to the evidence repository."""
    if envelope.artifact_type != FINDING_ARTIFACT_TYPE:
        raise ValueError(
            f"emit_finding() expects artifact_type='Finding', got '{envelope.artifact_type}'"
        )
    if not envelope.verify():
        raise ValueError(f"Finding evidence lineage mismatch for {envelope.artifact_hash}")
    return (repository or EvidenceRepository()).append_artifact(envelope)


def certify_finding(
    finding: Any,
    validation_hash: str,
    repository: EvidenceRepository,
    *,
    version: str = FINDING_EVIDENCE_VERSION,
    created_at: str = "",
) -> EvidenceEnvelope:
    """Certify a validated research finding against a successful Validation.

    The Validation must already exist in the evidence repository and must be
    stored as a ``Validation`` artifact.  The finding must also carry the
    canonical ``VALIDATED`` status.  This is deliberate: a finding can never
    become durable knowledge through this boundary without explicit validation.
    """
    validation = repository.get_artifact(validation_hash)
    if validation is None:
        raise ValueError(f"Validation artifact '{validation_hash}' not found in repository")
    if validation.artifact_type != VALIDATION_ARTIFACT_TYPE:
        raise ValueError(
            f"Finding certification requires a Validation artifact, got '{validation.artifact_type}'"
        )

    status = str(getattr(finding, "status", ""))
    if status != VALIDATED_STATUS:
        raise ValueError(
            f"Finding certification requires status='VALIDATED', got '{status or 'UNKNOWN'}'"
        )

    envelope = build_finding_envelope(
        finding,
        validation_hash=validation_hash,
        version=version,
        created_at=created_at,
    )
    return emit_finding(envelope, repository)


__all__ = [
    "FINDING_ARTIFACT_TYPE",
    "FINDING_EVIDENCE_VERSION",
    "VALIDATED_STATUS",
    "VALIDATION_ARTIFACT_TYPE",
    "VALIDATION_TO_FINDING_RELATION",
    "build_finding_envelope",
    "certify_finding",
    "emit_finding",
    "finding_hash",
    "finding_payload",
]
