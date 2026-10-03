"""Runtime certification for the Experiment → Run → Result evidence chain.

This module is the production trust boundary. A result is not certified unless
its real dataset evidence artifact exists first, the Experiment → Run → Result
lineage is append-only, and the complete chain verifies after emission.

Synthetic, demo, mock, and fixture inputs are explicitly rejected. Artifact
hashes are deterministic and intentionally exclude ``created_at`` telemetry.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from researchos.evidence.dataset_emission import build_dataset_envelope
from researchos.evidence.envelope import EvidenceEnvelope
from researchos.evidence.experiment_emission import build_experiment_envelope
from researchos.evidence.repository import EvidenceRepository
from researchos.evidence.result_emission import build_result_envelope
from researchos.evidence.run_emission import build_run_envelope


_SYNTHETIC_SOURCES = frozenset({"synthetic", "demo", "mock", "fixture"})


def _classification(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


def _is_synthetic_experiment(experiment: Any) -> bool:
    """Return whether an experiment is explicitly backed by synthetic data."""
    dataset_config = getattr(experiment, "dataset_config", None)
    if dataset_config is None:
        return False
    source = _classification(getattr(dataset_config, "source", ""))
    if source in _SYNTHETIC_SOURCES:
        return True
    parameters = getattr(dataset_config, "parameters", {})
    if isinstance(parameters, Mapping):
        classification = _classification(parameters.get("data_classification", ""))
        if classification in _SYNTHETIC_SOURCES:
            return True
    return False


def _is_synthetic_dataset(dataset: Any) -> bool:
    """Reject synthetic classification from the actual runtime dataset."""
    metadata = getattr(dataset, "metadata", {})
    if isinstance(metadata, Mapping):
        classification = _classification(metadata.get("data_classification", ""))
        if classification in _SYNTHETIC_SOURCES:
            return True
        source = _classification(metadata.get("source", ""))
        if source in _SYNTHETIC_SOURCES:
            return True
    source = _classification(getattr(dataset, "source", ""))
    return source in _SYNTHETIC_SOURCES


def _is_synthetic_envelope(envelope: EvidenceEnvelope) -> bool:
    """Inspect a persisted Dataset envelope before allowing it as a parent."""
    payload = envelope.payload if isinstance(envelope.payload, Mapping) else {}
    metadata = payload.get("metadata", {})
    if isinstance(metadata, Mapping):
        if _classification(metadata.get("data_classification", "")) in _SYNTHETIC_SOURCES:
            return True
        if _classification(metadata.get("source", "")) in _SYNTHETIC_SOURCES:
            return True
    source = _classification(payload.get("source", ""))
    return source in _SYNTHETIC_SOURCES


def _assert_evidence_eligible(experiment: Any, dataset: Any) -> None:
    """Fail closed before any artifact is written."""
    if _is_synthetic_experiment(experiment) or _is_synthetic_dataset(dataset):
        raise ValueError(
            "Synthetic, demo, mock, and fixture datasets cannot be certified as "
            "research evidence; use a validated real-market dataset."
        )


def _dataset_envelope(dataset: Any, *, version: str, created_at: str) -> EvidenceEnvelope:
    """Build the canonical Dataset parent or fail closed."""
    try:
        return build_dataset_envelope(dataset, version=version, created_at=created_at)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            "Runtime evidence certification requires a deterministic ResearchDataset "
            "contract with features, labels, metadata, and version."
        ) from exc


@dataclass(frozen=True)
class RuntimeCertification:
    """Immutable record of one certified Dataset → Experiment → Run → Result chain."""

    dataset: EvidenceEnvelope
    experiment: EvidenceEnvelope
    run: EvidenceEnvelope
    result: EvidenceEnvelope

    @property
    def dataset_hash(self) -> str:
        return self.dataset.artifact_hash

    @property
    def experiment_hash(self) -> str:
        return self.experiment.artifact_hash

    @property
    def run_hash(self) -> str:
        return self.run.artifact_hash

    @property
    def result_hash(self) -> str:
        return self.result.artifact_hash

    def verify(self, repository: EvidenceRepository) -> bool:
        """Verify stored artifacts and every expected lineage edge."""
        if not repository.verify_evidence():
            return False
        stored = tuple(
            repository.get_artifact(h)
            for h in (self.dataset_hash, self.experiment_hash, self.run_hash, self.result_hash)
        )
        if stored != (self.dataset, self.experiment, self.run, self.result):
            return False
        if self.experiment_hash not in repository.get_children(self.dataset_hash):
            return False
        if self.dataset_hash not in repository.get_parents(self.experiment_hash):
            return False
        if self.run_hash not in repository.get_children(self.experiment_hash):
            return False
        if self.experiment_hash not in repository.get_parents(self.run_hash):
            return False
        if self.result_hash not in repository.get_children(self.run_hash):
            return False
        if self.run_hash not in repository.get_parents(self.result_hash):
            return False
        return True


def certify_runtime(
    experiment: Any,
    run: Any,
    result: Any,
    repository: EvidenceRepository,
    *,
    dataset: Any | None = None,
    dataset_hash: str = "",
    backend_identity: Mapping[str, Any] | None = None,
    version: str = "1.0.0",
    created_at: str = "",
) -> RuntimeCertification:
    """Certify a complete Dataset → Experiment → Run → Result chain.

    Production certification requires either the actual deterministic dataset
    contract (preferred) or an already persisted Dataset evidence hash. When
    a dataset object is supplied, its canonical envelope is persisted before
    the Experiment artifact. No partial certification is returned: any
    emission or post-write verification failure raises immediately.

    ``created_at`` is observational telemetry only; it is never part of an
    artifact hash.
    """
    if not isinstance(repository, EvidenceRepository):
        raise TypeError("repository must be an EvidenceRepository")
    if dataset is None and not dataset_hash:
        raise ValueError("runtime evidence certification requires a Dataset evidence parent")
    dataset_envelope: EvidenceEnvelope

    if dataset is not None:
        _assert_evidence_eligible(experiment, dataset)
    elif _is_synthetic_experiment(experiment):
        raise ValueError(
            "Synthetic, demo, mock, and fixture datasets cannot be certified as research evidence"
        )

    if dataset is not None:
        dataset_envelope = _dataset_envelope(dataset, version=version, created_at=created_at)
        repository.append_artifact(dataset_envelope)
        dataset_parent_hash = dataset_envelope.artifact_hash
    else:
        dataset_parent_hash = dataset_hash
        dataset_envelope = repository.get_artifact(dataset_parent_hash)
        if dataset_envelope is None:
            raise ValueError(f"dataset evidence artifact '{dataset_parent_hash}' does not exist")
        if dataset_envelope.artifact_type != "Dataset":
            raise ValueError(f"dataset evidence artifact '{dataset_parent_hash}' is not a Dataset artifact")
        if _is_synthetic_envelope(dataset_envelope):
            raise ValueError(
                "Synthetic, demo, mock, and fixture datasets cannot be certified as research evidence"
            )

    experiment_envelope = build_experiment_envelope(
        experiment,
        version=version,
        created_at=created_at,
        parent_hashes=[dataset_parent_hash],
    )
    repository.append_artifact(experiment_envelope)

    run_envelope = build_run_envelope(
        run,
        experiment_hash=experiment_envelope.artifact_hash,
        backend_identity=backend_identity,
        version=version,
        created_at=created_at,
        parent_hashes=[experiment_envelope.artifact_hash],
    )
    repository.append_artifact(run_envelope)

    result_envelope = build_result_envelope(
        result,
        run_hash=run_envelope.artifact_hash,
        experiment_hash=experiment_envelope.artifact_hash,
        backend_identity=backend_identity,
        version=version,
        created_at=created_at,
        parent_hashes=[run_envelope.artifact_hash],
    )
    repository.append_artifact(result_envelope)

    certification = RuntimeCertification(
        dataset=dataset_envelope,
        experiment=experiment_envelope,
        run=run_envelope,
        result=result_envelope,
    )
    if not certification.verify(repository):
        raise RuntimeError("runtime evidence certification verification failed")
    return certification


__all__ = ["RuntimeCertification", "certify_runtime"]
