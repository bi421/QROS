"""
Experiment Evidence Emission — connect the existing Experiment contract to the evidence store.

Phase 5.3b.2 — Experiment Evidence Emission only.

This module bridges the existing ``Experiment`` contract (from
``researchos.experiments.experiment``) to the append-only ``EvidenceRepository``
by building a scheme-2 ``EvidenceEnvelope`` (``HASH_SCHEME_VERSION = "2"``) of
artifact type ``"Experiment"``.

Scope (strictly additive):
    - Build an Experiment evidence artifact from an existing ``Experiment``.
    - Capture experiment_hash, hypothesis identity, dataset references,
      dataset_config snapshot, simulation_config snapshot, and
      methodology/version metadata in the payload.
    - Preserve existing Experiment behavior (no mutation).
    - Do NOT emit Run or Result yet.
    - No execution changes.
    - No model registry.

Design:
    - The envelope payload is a deterministic, primitives-only projection of
      the Experiment definition (mirroring ``Experiment._to_hashable_dict``).
      ``created_at`` is telemetry and excluded from every hash.
    - ``build_experiment_envelope`` returns an immutable ``EvidenceEnvelope``
      whose ``artifact_hash`` is canonical (scheme 2).
    - ``emit_experiment`` appends the envelope to an ``EvidenceRepository``
      and records the Dataset → Experiment lineage edge when a dataset parent
      hash is supplied.
    - ``attach_dataset_parent(envelope, dataset_hash)`` returns a new envelope
      carrying the dataset artifact hash as a parent (lineage edge).

This is a certification/trust layer only — it computes no trading decisions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from researchos.evidence.envelope import (
    HASH_SCHEME_VERSION,
    EvidenceEnvelope,
    build_envelope,
)
from researchos.evidence.repository import EvidenceRepository

#: The evidence artifact_type emitted for experiments.
EXPERIMENT_ARTIFACT_TYPE = "Experiment"

#: Default methodology version for the experiment evidence surface.
EXPERIMENT_EVIDENCE_VERSION = "1.0.0"


def _to_primitives(value: Any) -> Any:
    """Recursively convert a value to a primitives-only representation.

    Mappings keep str keys; sequences become lists.  Any non-primitive leaf
    value is preserved as-is and the envelope's strict payload validation will
    reject it (so the caller learns of an unsupportable Experiment rather than
    silently coercing it).
    """
    if isinstance(value, Mapping):
        return {str(k): _to_primitives(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_primitives(v) for v in value]
    return value


def _config_to_dict(config: Any) -> dict[str, Any]:
    """Serialize a config object (DatasetConfig / SimulationConfig) to a dict.

    Returns an empty mapping when the config is absent or has no ``to_dict``.
    """
    if config is None:
        return {}
    to_dict = getattr(config, "to_dict", None)
    if to_dict is None:
        return {}
    result = to_dict()
    if not isinstance(result, dict):
        raise TypeError("config serialization must return a dictionary")
    return result


def experiment_payload(experiment: Any) -> dict[str, Any]:
    """Build a deterministic, primitives-only payload from an ``Experiment``.

    Mirrors ``Experiment._to_hashable_dict`` so the evidence identity is the
    canonical experiment definition.  ``created_at`` is intentionally NOT
    included (telemetry).

    Raises:
        TypeError: If ``experiment`` does not expose the expected attributes.
    """
    metric_definitions = sorted(
        [m.to_dict() for m in getattr(experiment, "metric_definitions", [])],
        key=lambda x: str(x.get("name", "")),
    )
    parameters = dict(getattr(experiment, "parameters", {}) or {})
    tags = sorted(getattr(experiment, "tags", []) or [])
    ontology_tags = sorted(getattr(experiment, "ontology_tags", []) or [])

    dataset_config = getattr(experiment, "dataset_config", None)
    simulation_config = getattr(experiment, "simulation_config", None)

    return {
        "experiment_hash": str(getattr(experiment, "experiment_hash", "")),
        "hypothesis_id": str(getattr(experiment, "hypothesis_id", "")),
        "name": str(getattr(experiment, "name", "")),
        "description": str(getattr(experiment, "description", "")),
        "experiment_type": str(getattr(experiment, "experiment_type", "")),
        "dataset_config": _to_primitives(_config_to_dict(dataset_config)),
        "simulation_config": _to_primitives(_config_to_dict(simulation_config)),
        "metric_definitions": _to_primitives(metric_definitions),
        "parameters": _to_primitives(parameters),
        "version": str(getattr(experiment, "version", "1.0.0")),
        "tags": tags,
        "experiment_trace": str(getattr(experiment, "experiment_trace", "")),
        "status": str(getattr(experiment, "status", "")),
        "ontology_tags": ontology_tags,
    }


def build_experiment_envelope(
    experiment: Any,
    version: str = EXPERIMENT_EVIDENCE_VERSION,
    created_at: str = "",
    parent_hashes: Sequence[str] | None = None,
) -> EvidenceEnvelope:
    """Build a scheme-2 ``EvidenceEnvelope`` for an ``Experiment``.

    The envelope binds ``artifact_type="Experiment"`` + ``version`` + payload
    into the ``artifact_hash`` (scheme 2), so:

        - the same experiment always produces the same ``artifact_hash``, and
        - a changed experiment (config/params) produces a different hash.

    Args:
        experiment: An ``Experiment`` (or any object exposing the attributes
            used by ``experiment_payload``).
        version: Methodology version for the experiment evidence surface.
        created_at: Observational telemetry (never hashed).
        parent_hashes: Optional input artifact hashes (e.g. a Dataset hash).

    Returns:
        An immutable ``EvidenceEnvelope`` ready for persistence.
    """
    payload = experiment_payload(experiment)
    return build_envelope(
        artifact_type=EXPERIMENT_ARTIFACT_TYPE,
        payload=payload,
        version=version,
        created_at=created_at,
        parent_hashes=parent_hashes,
    )


def attach_dataset_parent(
    envelope: EvidenceEnvelope,
    dataset_hash: str,
) -> EvidenceEnvelope:
    """Return a new Experiment envelope carrying a dataset parent (lineage).

    The returned envelope records ``dataset_hash`` as a parent so the
    EvidenceRepository writes a Dataset → Experiment lineage edge on append.
    The original envelope is unchanged (immutable).
    """
    parents = list(envelope.parent_hashes)
    if dataset_hash not in parents:
        parents.append(dataset_hash)
    return build_envelope(
        artifact_type=EXPERIMENT_ARTIFACT_TYPE,
        payload=envelope.payload,
        version=envelope.version,
        created_at=envelope.created_at,
        parent_hashes=parents,
    )


def emit_experiment(
    envelope: EvidenceEnvelope,
    repository: EvidenceRepository | None = None,
) -> EvidenceEnvelope:
    """Persist an Experiment envelope to an ``EvidenceRepository`` (append-only).

    Args:
        envelope: An Experiment ``EvidenceEnvelope`` (from
            ``build_experiment_envelope``).
        repository: An ``EvidenceRepository``; defaults to an in-memory one.

    Returns:
        The stored envelope.

    Raises:
        ValueError: If the envelope is not an Experiment artifact or fails
            verification.
    """
    if envelope.artifact_type != EXPERIMENT_ARTIFACT_TYPE:
        raise ValueError(f"emit_experiment() expects artifact_type='Experiment', got '{envelope.artifact_type}'")
    if not envelope.verify():
        raise ValueError(f"Experiment evidence lineage mismatch for {envelope.artifact_hash}")
    repo = repository or EvidenceRepository()
    return repo.append_artifact(envelope)


def emit_experiment_with_dataset(
    experiment: Any,
    dataset_hash: str,
    repository: EvidenceRepository | None = None,
    version: str = EXPERIMENT_EVIDENCE_VERSION,
    created_at: str = "",
) -> EvidenceEnvelope:
    """Convenience: build an Experiment envelope, link it to a Dataset, and emit.

    This records the Dataset → Experiment lineage edge atomically on append.

    Returns:
        The stored Experiment envelope.
    """
    base = build_experiment_envelope(
        experiment,
        version=version,
        created_at=created_at,
    )
    linked = attach_dataset_parent(base, dataset_hash)
    return emit_experiment(linked, repository)


__all__ = [
    "EXPERIMENT_ARTIFACT_TYPE",
    "EXPERIMENT_EVIDENCE_VERSION",
    "HASH_SCHEME_VERSION",
    "attach_dataset_parent",
    "build_experiment_envelope",
    "emit_experiment",
    "emit_experiment_with_dataset",
    "experiment_payload",
]
