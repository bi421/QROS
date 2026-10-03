"""
ReproductionEngine — deterministic reproduction of certified Result artifacts.

Phase 5.3c Step 3 — Reproduction Engine implementation.

This module provides the ``ReproductionEngine``, which takes a certified
``Result`` artifact hash, resolves its full lineage
(Dataset → Experiment → Run → Result → Validation), verifies every artifact's
integrity, reconstructs the exact inputs from the stored evidence payloads,
re-executes through the certified ``BaseExperimentRunner`` boundary, and
compares the original and reproduced ``result_hash`` values to validate
deterministic reproducibility.

Workflow:
    1. Resolve complete lineage via ``LineageQueryEngine.resolve_full_chain()``.
    2. Verify every artifact's integrity (``verify()``).
    3. Reconstruct:
       - ``ResearchDataset.from_payload()`` from the Dataset payload.
       - ``DatasetConfig.from_dict()`` and ``SimulationConfig.from_dict()``
         from the Run payload's config snapshots.
       - ``Experiment`` from the Experiment payload.
    4. Execute through ``BaseExperimentRunner`` (the certified Python reference).
    5. Generate a new ``ExperimentResult``.
    6. Compare the original ``result_hash`` and reproduced ``result_hash``.

Failure handling:
    All expected reproduction failures raise typed exceptions (subclasses of
    ``ReproductionError``) — never generic ``Exception``:

    - ``MissingArtifact`` — an artifact in the required chain is not present.
    - ``IntegrityFailure`` — an artifact's ``verify()`` check fails.
    - ``ReconstructionFailure`` — a payload cannot be reconstructed into its
      typed contract (invalid payload, bad config, etc.).
    - ``ExecutionFailure`` — the certified execution path fails.
    - ``HashMismatch`` — the reproduced ``result_hash`` differs from the
      original.

On success, ``reproduce()`` returns a ``ReproductionReport`` with
``success=True`` and the identical ``reproduced_hash``.

Constraints:
    - Additive only: never modifies ``EvidenceEnvelope``, ``EvidenceRepository``,
      lineage schema, or any frozen contract.
    - No trading logic, broker integration, ML/model registry, or C++ changes.
    - The output ``ReproductionReport`` is deterministic for identical inputs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from researchos.evidence.envelope import EvidenceEnvelope
from researchos.evidence.lineage import FullChain, LineageQueryEngine
from researchos.evidence.repository import EvidenceRepository
from researchos.experiments.contracts import DatasetConfig, SimulationConfig
from researchos.experiments.experiment import Experiment
from researchos.experiments.runner import BaseExperimentRunner
from researchos.quant_engine.machine_learning.dataset_contracts import (
    ResearchDataset,
)

# =========================================================================
# Runner-dataset marshalling
# =========================================================================


def research_dataset_to_runner_dataset(dataset: ResearchDataset) -> list[dict[str, float]]:
    """Deterministically convert a ``ResearchDataset`` into the OHLCV contract
    the certified ``BaseExperimentRunner`` boundary normalizes.

    The runner's backend ``_extract_prices`` consumes ``List[dict]`` with a
    ``close`` key.  This marshalling is a pure, deterministic function of the
    dataset's feature matrix: identical research datasets always produce an
    identical runner dataset, so the runner's dataset-provenance hash (and
    therefore the reproduced ``result_hash``) is preserved.

    When the dataset has no feature rows, a deterministic 252-period synthetic
    series is produced (consistent with the backend's ``None`` fallback).
    """
    feature_rows = list(getattr(dataset, "features", ()) or ())
    if not feature_rows:
        base = 100.0
        return [
            {
                "open": base + i * 0.1,
                "high": base + i * 0.1 + 1.0,
                "low": base + i * 0.1 - 0.5,
                "close": base + i * 0.1 + 0.25,
                "volume": 1000.0 + i,
            }
            for i in range(252)
        ]
    bars: list[dict[str, float]] = []
    for row in feature_rows:
        row_values = list(row)
        close = float(row_values[0]) if row_values else 100.0
        bars.append(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 0.5,
                "close": close,
                "volume": 1000.0,
            }
        )
    return bars


# =========================================================================
# Typed failures
# =========================================================================


class ReproductionError(Exception):
    """Base class for all expected reproduction failures."""


class MissingArtifact(ReproductionError):
    """Raised when a required artifact is not present in the evidence store."""


class IntegrityFailure(ReproductionError):
    """Raised when an artifact's integrity check (``verify()``) fails."""


class ReconstructionFailure(ReproductionError):
    """Raised when a payload cannot be reconstructed into its typed contract."""


class ExecutionFailure(ReproductionError):
    """Raised when the certified execution path fails."""


class HashMismatch(ReproductionError):
    """Raised when the reproduced ``result_hash`` differs from the original."""


# =========================================================================
# ReproductionReport
# =========================================================================


@dataclass(frozen=True)
class ReproductionReport:
    """Deterministic report of a successful reproduction.

    Attributes:
        success: True when the reproduction produced an identical
            ``result_hash``.
        original_hash: The ``artifact_hash`` of the original Result artifact.
        reproduced_hash: The ``result_hash`` of the newly reproduced
            ``ExperimentResult``.
        artifact_chain: Mapping of artifact type → artifact hash for the
            resolved lineage chain.
        verification_errors: List of verification error messages (empty on
            success).
        divergence_details: Mapping of divergence details (empty on success).
    """

    success: bool
    original_hash: str
    reproduced_hash: str = ""
    artifact_chain: dict[str, str] = field(default_factory=dict)
    verification_errors: list[str] = field(default_factory=list)
    divergence_details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "original_hash": self.original_hash,
            "reproduced_hash": self.reproduced_hash,
            "artifact_chain": dict(self.artifact_chain),
            "verification_errors": list(self.verification_errors),
            "divergence_details": dict(self.divergence_details),
        }


# =========================================================================
# ReproductionEngine
# =========================================================================


class ReproductionEngine:
    """Deterministic reproduction of certified Result artifacts.

    Args:
        repository: An ``EvidenceRepository`` (defaults to in-memory).
        lineage_engine: A ``LineageQueryEngine`` (defaults to one constructed
            from the repository).
        runner: A ``BaseExperimentRunner`` (defaults to a fresh instance).
    """

    def __init__(
        self,
        repository: EvidenceRepository | None = None,
        lineage_engine: LineageQueryEngine | None = None,
        runner: BaseExperimentRunner | None = None,
    ) -> None:
        self._repo = repository or EvidenceRepository()
        self._lineage = lineage_engine or LineageQueryEngine(repository=self._repo)
        self._runner = runner or BaseExperimentRunner()

    def reproduce(self, result_hash: str) -> ReproductionReport:
        """Reproduce a certified Result artifact.

        Args:
            result_hash: The ``artifact_hash`` of a ``Result`` evidence
                envelope.

        Returns:
            A ``ReproductionReport`` with ``success=True`` and an identical
            ``reproduced_hash``.

        Raises:
            ReproductionError subclasses for expected failures (see class
            docstring).  In particular ``MissingArtifact``, ``IntegrityFailure``,
            ``ReconstructionFailure``, ``ExecutionFailure``, ``HashMismatch``.
        """
        # ---------------------------------------------------------------
        # 1. Resolve lineage
        # ---------------------------------------------------------------
        chain = self._lineage.resolve_full_chain(result_hash)
        if chain is None:
            raise MissingArtifact(f"Result artifact {result_hash} is not a Result or is not present in the evidence store")
        self._assert_chain(chain, result_hash)

        # Build artifact_chain for the report.
        artifact_chain: dict[str, str] = {}
        for typ, env in [
            ("Dataset", chain.dataset),
            ("Experiment", chain.experiment),
            ("Run", chain.run),
            ("Result", chain.result),
            ("Validation", chain.validation),
        ]:
            if env is not None:
                artifact_chain[typ] = env.artifact_hash

        # ---------------------------------------------------------------
        # 2. Verify artifact integrity
        # ---------------------------------------------------------------
        for typ, env in [
            ("Dataset", chain.dataset),
            ("Experiment", chain.experiment),
            ("Run", chain.run),
            ("Result", chain.result),
            ("Validation", chain.validation),
        ]:
            if env is not None and not env.verify():
                raise IntegrityFailure(f"{typ} artifact {env.artifact_hash} failed integrity verification (lineage_hash mismatch)")

        # ---------------------------------------------------------------
        # 3. Reconstruct inputs
        # ---------------------------------------------------------------
        dataset = self._reconstruct_dataset(chain.dataset)
        dataset_config = self._reconstruct_dataset_config(chain.run)
        simulation_config = self._reconstruct_simulation_config(chain.run)
        experiment = self._reconstruct_experiment(chain.experiment, dataset_config, simulation_config)

        # Convert the reconstructed research dataset into the runner-consumable
        # OHLCV contract the certified boundary normalizes.
        runner_dataset = research_dataset_to_runner_dataset(dataset)

        # ---------------------------------------------------------------
        # 4. Execute through certified boundary
        # ---------------------------------------------------------------
        try:
            _, reproduced_result = self._runner.run(experiment, runner_dataset)
        except Exception as e:
            raise ExecutionFailure(f"Certified execution failed during reproduction: {e}") from e

        # ---------------------------------------------------------------
        # 5. Extract original result_hash
        # ---------------------------------------------------------------
        if chain.result is None:
            raise ReconstructionFailure("Result envelope is None")
        if chain.result is None:
            raise ReconstructionFailure("Result envelope is None")
        payload = chain.result.payload
        if not isinstance(payload, Mapping):
            raise ReconstructionFailure(f"Result payload is not a mapping: {type(payload).__name__}")
        original_result_hash = str(payload.get("result_hash", ""))

        reproduced_hash = reproduced_result.result_hash

        # ---------------------------------------------------------------
        # 6. Compare hashes
        # ---------------------------------------------------------------
        if not original_result_hash:
            raise ReconstructionFailure("Result artifact payload does not carry a 'result_hash' reference to compare against")

        if original_result_hash != reproduced_hash:
            raise HashMismatch(f"Reproduction hash mismatch: original={original_result_hash} reproduced={reproduced_hash}")

        # Success: identical hashes.
        return ReproductionReport(
            success=True,
            original_hash=result_hash,
            reproduced_hash=reproduced_hash,
            artifact_chain=artifact_chain,
        )

    # ── chain validation helpers ─────────────────────────────────────────

    @staticmethod
    def _assert_chain(chain: FullChain, result_hash: str) -> None:
        """Assert that the chain contains all required artifacts.

        Raises ``MissingArtifact`` when any required artifact is missing.
        """
        missing: list[str] = []
        if chain.dataset is None:
            missing.append("Dataset")
        if chain.experiment is None:
            missing.append("Experiment")
        if chain.run is None:
            missing.append("Run")
        if chain.result is None:
            missing.append("Result")
        if missing:
            raise MissingArtifact(f"Cannot reproduce {result_hash}: missing chain artifacts {missing}. Ensure all required artifacts are stored in the evidence repository.")

    # ── reconstruction helpers ───────────────────────────────────────────

    @staticmethod
    def _reconstruct_dataset(
        dataset_env: EvidenceEnvelope | None,
    ) -> ResearchDataset:
        """Reconstruct a ``ResearchDataset`` from a Dataset evidence envelope.

        Raises ``ReconstructionFailure`` when the payload is invalid.
        """
        if dataset_env is None:
            raise ReconstructionFailure("Dataset envelope is None")
        payload = dataset_env.payload
        if not isinstance(payload, Mapping):
            raise ReconstructionFailure(f"Dataset payload is not a mapping: {type(payload).__name__}")
        try:
            return ResearchDataset.from_payload(payload)
        except (TypeError, ValueError) as e:
            raise ReconstructionFailure(f"Failed to reconstruct ResearchDataset: {e}") from e

    @staticmethod
    def _reconstruct_dataset_config(
        run_env: EvidenceEnvelope | None,
    ) -> DatasetConfig:
        """Reconstruct a ``DatasetConfig`` from a Run envelope's payload.

        The Run payload carries a ``dataset_config`` snapshot.
        Raises ``ReconstructionFailure`` when the snapshot is missing or
        invalid.
        """
        if run_env is None:
            raise ReconstructionFailure("Run envelope is None")
        payload = run_env.payload
        if not isinstance(payload, Mapping):
            raise ReconstructionFailure(f"Run payload is not a mapping: {type(payload).__name__}")
        config_data = payload.get("dataset_config")
        if not isinstance(config_data, Mapping):
            raise ReconstructionFailure("Run payload does not contain a valid dataset_config mapping")
        try:
            return DatasetConfig.from_dict(dict(config_data))
        except (TypeError, ValueError, KeyError) as e:
            raise ReconstructionFailure(f"Failed to reconstruct DatasetConfig: {e}") from e

    @staticmethod
    def _reconstruct_simulation_config(
        run_env: EvidenceEnvelope | None,
    ) -> SimulationConfig:
        """Reconstruct a ``SimulationConfig`` from a Run envelope's payload.

        The Run payload carries a ``simulation_config`` snapshot.
        Raises ``ReconstructionFailure`` when the snapshot is missing or
        invalid.
        """
        if run_env is None:
            raise ReconstructionFailure("Run envelope is None")
        payload = run_env.payload
        if not isinstance(payload, Mapping):
            raise ReconstructionFailure(f"Run payload is not a mapping: {type(payload).__name__}")
        config_data = payload.get("simulation_config")
        if not isinstance(config_data, Mapping):
            raise ReconstructionFailure("Run payload does not contain a valid simulation_config mapping")
        try:
            return SimulationConfig.from_dict(dict(config_data))
        except (TypeError, ValueError, KeyError) as e:
            raise ReconstructionFailure(f"Failed to reconstruct SimulationConfig: {e}") from e

    @staticmethod
    def _reconstruct_experiment(
        experiment_env: EvidenceEnvelope | None,
        dataset_config: DatasetConfig,
        simulation_config: SimulationConfig,
    ) -> Experiment:
        """Reconstruct an ``Experiment`` from an Experiment evidence envelope.

        The Experiment payload carries the fields needed to build an
        ``Experiment`` in ``Ready`` status: hypothesis_id, name, description,
        experiment_type, metric_definitions, parameters, version, tags,
        ontology_tags, experiment_trace.

        Raises ``ReconstructionFailure`` when the payload is missing required
        fields.
        """
        if experiment_env is None:
            raise ReconstructionFailure("Experiment envelope is None")
        payload = experiment_env.payload
        if not isinstance(payload, Mapping):
            raise ReconstructionFailure(f"Experiment payload is not a mapping: {type(payload).__name__}")

        hypothesis_id = payload.get("hypothesis_id", "")
        if not hypothesis_id:
            raise ReconstructionFailure("Experiment payload is missing required 'hypothesis_id' field")

        try:
            from researchos.experiments.contracts import MetricDefinition

            experiment = Experiment(
                hypothesis_id=str(hypothesis_id),
                name=str(payload.get("name", "")),
                description=str(payload.get("description", "")),
                experiment_type=str(payload.get("experiment_type", "Backtest")),
                dataset_config=dataset_config,
                simulation_config=simulation_config,
                metric_definitions=[MetricDefinition.from_dict(m) for m in payload.get("metric_definitions", [])],
                parameters=dict(payload.get("parameters", {})),
                version=str(payload.get("version", "1.0.0")),
                tags=list(payload.get("tags", [])),
                ontology_tags=list(payload.get("ontology_tags", [])),
                experiment_trace=str(payload.get("experiment_trace", "")),
            )
            experiment.mark_ready()
            return experiment
        except (TypeError, ValueError, KeyError) as e:
            raise ReconstructionFailure(f"Failed to reconstruct Experiment: {e}") from e


__all__ = [
    "ReproductionEngine",
    "ReproductionReport",
    "ReproductionError",
    "MissingArtifact",
    "IntegrityFailure",
    "ReconstructionFailure",
    "ExecutionFailure",
    "HashMismatch",
    "research_dataset_to_runner_dataset",
]
