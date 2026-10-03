"""
Run Evidence Emission — connect the existing ExperimentRun contract to the evidence store.

Phase 5.3b.3 — ExperimentRun Evidence Emission only.

This module bridges the existing ``ExperimentRun`` contract (from
``researchos.experiments.result``) to the append-only ``EvidenceRepository`` by
building a scheme-2 ``EvidenceEnvelope`` (``HASH_SCHEME_VERSION = "2"``) of
artifact type ``"Run"``.

Scope (strictly additive):
    - Build a Run evidence artifact from an existing ``ExperimentRun``.
    - Capture run_hash, experiment_id, experiment_hash reference, parameters
      snapshot, dataset_config snapshot, simulation_config snapshot, backend
      identity metadata, and deterministic run metadata.
    - EXCLUDE wall-clock telemetry, execution timestamps, and runtime duration
      from identity fields.
    - Preserve existing ExperimentRun behavior (no mutation).
    - Do NOT emit Result / Validation / Model yet.
    - No execution changes.
    - No model registry.

Design:
    - The envelope payload is a deterministic, primitives-only projection of
      the run's logical identity.  ``created_at`` and any wall-clock
      timestamps (``started_at`` / ``completed_at``) are telemetry and
      excluded from every hash.  Runtime duration is excluded because it is
      observational performance, not logical identity.
    - ``build_run_envelope`` returns an immutable ``EvidenceEnvelope`` whose
      ``artifact_hash`` is canonical (scheme 2).
    - ``emit_run`` appends the envelope to an ``EvidenceRepository`` and
      records the Experiment → Run lineage edge (relation ``"executes"``)
      when an experiment parent hash is supplied.
    - ``attach_experiment_parent(envelope, experiment_hash)`` returns a new
      envelope carrying the experiment artifact hash as a parent (lineage).

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

#: The evidence artifact_type emitted for runs.
RUN_ARTIFACT_TYPE = "Run"

#: Default methodology version for the run evidence surface.
RUN_EVIDENCE_VERSION = "1.0.0"

#: Canonical lineage relation label for Experiment → Run.
EXPERIMENT_TO_RUN_RELATION = "executes"


def _to_primitives(value: Any) -> Any:
    """Recursively convert a value to a primitives-only representation.

    Mappings keep str keys; sequences become lists.  Any non-primitive leaf
    value is preserved as-is and the envelope's strict payload validation will
    reject it (so the caller learns of an unsupportable Run rather than
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


def run_payload(
    run: Any,
    experiment_hash: str = "",
    backend_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic, primitives-only payload from an ``ExperimentRun``.

    The payload captures the run's LOGICAL identity only.  Wall-clock
    telemetry (``started_at`` / ``completed_at``) and runtime duration are
    intentionally excluded so identical logical runs always hash identically.

    Args:
        run: An ``ExperimentRun`` (or any object exposing the expected
            attributes).
        experiment_hash: The experiment's deterministic artifact/reference
            hash (from the owning ``Experiment``), recorded as a reference.
        backend_identity: Optional backend identity metadata (name, version,
            etc.) recorded as observation of which backend produced the run.

    Returns:
        A primitives-only payload ready for hashing.
    """
    dataset_config = getattr(run, "dataset_config", None)
    simulation_config = getattr(run, "simulation_config", None)
    parameters = dict(getattr(run, "parameters", {}) or {})
    tags = sorted(getattr(run, "tags", []) or [])
    ontology_tags = sorted(getattr(run, "ontology_tags", []) or [])

    payload: dict[str, Any] = {
        "run_hash": str(getattr(run, "run_hash", "")),
        "experiment_id": str(getattr(run, "experiment_id", "")),
        "experiment_hash": experiment_hash,
        "run_number": int(getattr(run, "run_number", 1)),
        "dataset_config": _to_primitives(_config_to_dict(dataset_config)),
        "simulation_config": _to_primitives(_config_to_dict(simulation_config)),
        "parameters": _to_primitives(parameters),
        "status": str(getattr(run, "status", "")),
        "trace": str(getattr(run, "trace", "")),
        "tags": tags,
        "ontology_tags": ontology_tags,
    }
    if backend_identity is not None:
        payload["backend_identity"] = _to_primitives(dict(backend_identity))
    return payload


def build_run_envelope(
    run: Any,
    experiment_hash: str = "",
    backend_identity: Mapping[str, Any] | None = None,
    version: str = RUN_EVIDENCE_VERSION,
    created_at: str = "",
    parent_hashes: Sequence[str] | None = None,
) -> EvidenceEnvelope:
    """Build a scheme-2 ``EvidenceEnvelope`` for an ``ExperimentRun``.

    The envelope binds ``artifact_type="Run"`` + ``version`` + payload into
    the ``artifact_hash`` (scheme 2), so:

        - identical runs (same logical inputs) → identical ``artifact_hash``, and
        - a changed logical input → a different ``artifact_hash``.

    Runtime timing / wall-clock telemetry never affects the hash.

    Args:
        run: An ``ExperimentRun``.
        experiment_hash: The experiment's deterministic hash (reference).
        backend_identity: Optional backend identity metadata.
        version: Methodology version for the run evidence surface.
        created_at: Observational telemetry (never hashed).
        parent_hashes: Optional input artifact hashes (e.g. the Experiment hash).

    Returns:
        An immutable ``EvidenceEnvelope`` ready for persistence.
    """
    payload = run_payload(
        run,
        experiment_hash=experiment_hash,
        backend_identity=backend_identity,
    )
    return build_envelope(
        artifact_type=RUN_ARTIFACT_TYPE,
        payload=payload,
        version=version,
        created_at=created_at,
        parent_hashes=parent_hashes,
    )


def attach_experiment_parent(
    envelope: EvidenceEnvelope,
    experiment_hash: str,
) -> EvidenceEnvelope:
    """Return a new Run envelope carrying an experiment parent (lineage).

    The returned envelope records ``experiment_hash`` as a parent so the
    EvidenceRepository writes an Experiment → Run lineage edge (relation
    ``"executes"``) on append.  The original envelope is unchanged
    (immutable).
    """
    parents = list(envelope.parent_hashes)
    if experiment_hash not in parents:
        parents.append(experiment_hash)
    return build_envelope(
        artifact_type=RUN_ARTIFACT_TYPE,
        payload=envelope.payload,
        version=envelope.version,
        created_at=envelope.created_at,
        parent_hashes=parents,
    )


def emit_run(
    envelope: EvidenceEnvelope,
    repository: EvidenceRepository | None = None,
) -> EvidenceEnvelope:
    """Persist a Run envelope to an ``EvidenceRepository`` (append-only).

    Args:
        envelope: A Run ``EvidenceEnvelope`` (from ``build_run_envelope``).
        repository: An ``EvidenceRepository``; defaults to an in-memory one.

    Returns:
        The stored envelope.

    Raises:
        ValueError: If the envelope is not a Run artifact or fails
            verification.
    """
    if envelope.artifact_type != RUN_ARTIFACT_TYPE:
        raise ValueError(f"emit_run() expects artifact_type='Run', got '{envelope.artifact_type}'")
    if not envelope.verify():
        raise ValueError(f"Run evidence lineage mismatch for {envelope.artifact_hash}")
    repo = repository or EvidenceRepository()
    return repo.append_artifact(envelope)


def emit_run_for_experiment(
    run: Any,
    experiment_hash: str,
    repository: EvidenceRepository | None = None,
    backend_identity: Mapping[str, Any] | None = None,
    version: str = RUN_EVIDENCE_VERSION,
    created_at: str = "",
) -> EvidenceEnvelope:
    """Convenience: build a Run envelope, link it to an Experiment, and emit.

    This records the Experiment → Run lineage edge (relation ``"executes"``)
    atomically on append.

    Returns:
        The stored Run envelope.
    """
    base = build_run_envelope(
        run,
        experiment_hash=experiment_hash,
        backend_identity=backend_identity,
        version=version,
        created_at=created_at,
    )
    linked = attach_experiment_parent(base, experiment_hash)
    return emit_run(linked, repository)


__all__ = [
    "EXPERIMENT_TO_RUN_RELATION",
    "HASH_SCHEME_VERSION",
    "RUN_ARTIFACT_TYPE",
    "RUN_EVIDENCE_VERSION",
    "attach_experiment_parent",
    "build_run_envelope",
    "emit_run",
    "emit_run_for_experiment",
    "run_payload",
]
