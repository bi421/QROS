"""
Research Orchestration Layer (Q14) — the pure coordinator.

``ResearchOrchestrator`` wires the locked modules into a single deterministic
research pipeline:

    DatasetBuilder  →  WalkForwardValidator  →  Trainer  →  PipelineReport

The orchestrator is a PURE COORDINATOR.  It never persists, never writes to
repositories or registries, and never constructs or mutates graphs.  It
returns an immutable ``PipelineReport`` that carries the produced registry-
style ``ModelContract`` plus evidence descriptors for downstream layers.

Design rules:
    - Dependency injection only; no singletons; no global state.
    - stdlib only; deterministic; no randomness.
    - No modifications to locked modules.
    - No persistence, no side effects.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from researchos.quant_engine.machine_learning.dataset_builder import DatasetBuilder
from researchos.quant_engine.machine_learning.dataset_contracts import (
    ResearchDataset,
)
from researchos.quant_engine.models.contracts import (
    ModelContract as RegistryModelContract,
)
from researchos.quant_engine.training.contracts import (
    ModelContract as TrainingModelContract,
)
from researchos.quant_engine.training.contracts import (
    ModelType as TrainingModelType,
)
from researchos.quant_engine.training.trainer import TrainConfig, Trainer
from researchos.quant_engine.training.training_result import TrainingResult
from researchos.quant_engine.validation.contracts import (
    ValidationResult,
)
from researchos.quant_engine.validation.walk_forward import WalkForwardValidator

from .contracts import (
    ORCHESTRATION_VERSION,
    EvidenceEdgeDescriptor,
    EvidenceNodeDescriptor,
    OrchestrationError,
    PipelineReport,
    PipelineStatus,
)
from .parallel import (
    ParallelResearchExecutor,
    ResearchBranch,
    ResearchWave,
)

# ---------------------------------------------------------------------------
# deterministic helpers
# ---------------------------------------------------------------------------


def _make_pipeline_id(
    close: list[float],
    high: list[float],
    low: list[float],
    volume: list[float],
    model_id: str,
    train_size: int,
    validation_size: int,
    step_size: int,
) -> str:
    """Deterministic SHA-256 pipeline identifier derived from inputs."""
    payload = {
        "close_len": len(close),
        "close_start": close[0] if close else 0.0,
        "close_end": close[-1] if close else 0.0,
        "model_id": model_id,
        "train_size": train_size,
        "validation_size": validation_size,
        "step_size": step_size,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _make_node_id(
    prefix: str,
    dataset_hash: str,
    model_id: str,
) -> str:
    """Deterministic node identifier derived from hash and model id."""
    seed = f"{prefix}|{dataset_hash}|{model_id}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _make_edge_id(source_id: str, target_id: str, relationship: str) -> str:
    """Deterministic edge identifier derived from source, target, relationship."""
    seed = f"{source_id}|{target_id}|{relationship}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _dataset_hash(dataset: ResearchDataset) -> str:
    """Deterministic SHA-256 hash of a research dataset's content."""
    payload = {
        "feature_names": list(dataset.feature_names),
        "features": [list(row) for row in dataset.features],
        "labels": list(dataset.labels),
        "label_name": dataset.label_name,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# ---------------------------------------------------------------------------
# orchestrator
# ---------------------------------------------------------------------------


class ResearchOrchestrator:
    """Dependency-injected research pipeline coordinator.

    Wires the locked modules into a single deterministic pipeline, returning
    an immutable ``PipelineReport``.  No persistence, no side effects.

    Parameters:
        dataset_builder: ``DatasetBuilder`` instance (or None for default).
        validator: ``WalkForwardValidator`` instance (or None for default).
        trainer: ``Trainer`` instance (or None for default).
        parallel_executor: Optional executor used for dependency-wave orchestration.
            When omitted, a default two-worker executor is created for the
            validation/training wave.
    """

    def __init__(
        self,
        dataset_builder: DatasetBuilder | None = None,
        validator: WalkForwardValidator | None = None,
        trainer: Trainer | None = None,
        parallel_executor: ParallelResearchExecutor | None = None,
    ) -> None:
        self._dataset_builder = dataset_builder
        self._validator = validator
        self._trainer = trainer
        self._parallel_executor = parallel_executor

    # ------------------------------------------------------------------
    # step-by-step pipeline methods
    # ------------------------------------------------------------------

    def build_dataset(
        self,
        close: list[float],
        high: list[float],
        low: list[float],
        volume: list[float],
        *,
        label_horizon: int = 1,
        label_type: str = "binary",
    ) -> ResearchDataset:
        """Build a research dataset from OHLCV data.

        Delegates to ``DatasetBuilder``.  Accepts raw lists and a label
        horizon / type selector.

        Args:
            close: Close price series.
            high: High price series.
            low: Low price series.
            volume: Volume series.
            label_horizon: Look-ahead horizon for label computation.
            label_type: ``"binary"``, ``"regression"``, or ``"multiclass"``.

        Returns:
            An aligned ``ResearchDataset``.
        """
        builder = self._dataset_builder or DatasetBuilder(close, high, low, volume)

        if label_type == "binary":
            return builder.build_with_binary_labels(horizon=label_horizon)
        if label_type == "regression":
            return builder.build_with_future_return(horizon=label_horizon)
        if label_type == "multiclass":
            return builder.build_with_multiclass(horizon=label_horizon)

        raise OrchestrationError(f"unknown label_type: {label_type!r}; expected 'binary', 'regression', or 'multiclass'")

    def validate(
        self,
        dataset: ResearchDataset,
        *,
        train_size: int,
        validation_size: int,
        step_size: int,
    ) -> ValidationResult:
        """Run walk-forward validation on a research dataset.

        Delegates to ``WalkForwardValidator``.

        Args:
            dataset: The research dataset to validate.
            train_size: Samples per training window.
            validation_size: Samples per validation window.
            step_size: Window slide step between folds.

        Returns:
            An immutable ``ValidationResult``.
        """
        validator = self._validator or WalkForwardValidator(
            train_size=train_size,
            validation_size=validation_size,
            step_size=step_size,
        )
        return validator.validate(dataset)

    def train(
        self,
        dataset: ResearchDataset,
        *,
        model_id: str,
        name: str = "",
        model_type: str = "feature_weight",
        version: str = "1.0.0",
        created_at: str = "",
    ) -> TrainingResult:
        """Train a deterministic research model on a dataset.

        Delegates to ``Trainer``.

        Args:
            dataset: The research dataset to train on.
            model_id: Stable model identifier.
            name: Human-readable model name.
            model_type: ``"rule_based"``, ``"linear_formula"``, ``"threshold"``,
                or ``"feature_weight"``.
            version: Semantic version string.
            created_at: Deterministic creation timestamp.

        Returns:
            An immutable ``TrainingResult``.
        """
        trainer = self._trainer or Trainer()

        # Map model_type string to ModelType enum.
        mt = TrainingModelType.from_value(model_type)

        cfg = TrainConfig(
            model_id=model_id,
            name=name or model_id,
            version=version,
            model_type=mt,
            label_name=dataset.label_name,
            created_at=created_at,
        )

        return trainer.train(dataset, cfg)

    # ------------------------------------------------------------------
    # full pipeline
    # ------------------------------------------------------------------

    def run_pipeline(
        self,
        close: list[float],
        high: list[float],
        low: list[float],
        volume: list[float],
        *,
        # label configuration
        label_horizon: int = 1,
        label_type: str = "binary",
        # validation configuration
        train_size: int,
        validation_size: int,
        step_size: int,
        # training configuration
        model_id: str,
        model_name: str = "",
        model_type: str = "feature_weight",
        model_version: str = "1.0.0",
        created_at: str = "",
        # pipeline metadata
        metadata: Mapping[str, Any] | None = None,
    ) -> PipelineReport:
        """Execute the full research pipeline and return an immutable report.

        Pipeline steps:
            1. Build dataset from OHLCV (DatasetBuilder).
            2. Run walk-forward validation (WalkForwardValidator).
            3. Train deterministic model (Trainer).
            4. Build registry-style ModelContract, evidence descriptors.
            5. Return immutable PipelineReport.

        Args:
            close: Close price series.
            high: High price series.
            low: Low price series.
            volume: Volume series.
            label_horizon: Look-ahead horizon for label computation.
            label_type: ``"binary"``, ``"regression"``, or ``"multiclass"``.
            train_size: Samples per training window.
            validation_size: Samples per validation window.
            step_size: Window slide step between folds.
            model_id: Stable model identifier.
            model_name: Human-readable model name.
            model_type: Model family string.
            model_version: Semantic version.
            created_at: Deterministic creation timestamp.
            metadata: Additional pipeline metadata.

        Returns:
            An immutable ``PipelineReport`` with all stage outputs.
        """
        try:
            # Step 1: Build dataset.
            dataset = self.build_dataset(
                close,
                high,
                low,
                volume,
                label_horizon=label_horizon,
                label_type=label_type,
            )
            dhash = _dataset_hash(dataset)

            # Step 2: Validation and training are independent after the
            # immutable dataset snapshot exists. Run them as one parallel
            # wave. Result order is fixed by branch declaration, not timing.
            parallel = self._parallel_executor or ParallelResearchExecutor(
                max_workers=2
            )
            wave = ResearchWave(
                wave_id="dataset-derived-analysis",
                branches=(
                    ResearchBranch(
                        branch_id="validation",
                        run=lambda _ctx: self.validate(
                            dataset,
                            train_size=train_size,
                            validation_size=validation_size,
                            step_size=step_size,
                        ),
                    ),
                    ResearchBranch(
                        branch_id="training",
                        run=lambda _ctx: self.train(
                            dataset,
                            model_id=model_id,
                            name=model_name or model_id,
                            model_type=model_type,
                            version=model_version,
                            created_at=created_at,
                        ),
                    ),
                ),
            )
            parallel_result = parallel.run((wave,))
            branch_results = parallel_result.by_branch_id()
            validation = branch_results["validation"]
            training = branch_results["training"]
            validation_hash_str = hashlib.sha256(
                json.dumps(
                    validation.to_dict(),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()

            # Step 3: Build registry-style ModelContract.
            # The training module's ModelContract has .parameters, .training_hash
            # The registry module's ModelContract has .algorithm, .dataset_hash, .validation_hash
            training_model = training.model
            model_contract = RegistryModelContract(
                model_id=model_id,
                name=model_name or model_id,
                version=model_version,
                algorithm=model_type,
                feature_names=tuple(dataset.feature_names),
                label_name=dataset.label_name,
                dataset_hash=dhash,
                validation_hash=validation_hash_str,
                parameters=dict(training_model.parameters),
                created_at=created_at,
                metadata={
                    "orchestration_version": ORCHESTRATION_VERSION,
                    "training_hash": training_model.training_hash,
                    "model_type": model_type,
                },
            )

            # Step 5: Build evidence descriptors (pure, for downstream consumption).
            pipeline_id = _make_pipeline_id(
                close,
                high,
                low,
                volume,
                model_id,
                train_size,
                validation_size,
                step_size,
            )

            dataset_node_id = _make_node_id("dataset", dhash, model_id)
            model_node_id = _make_node_id("model", dhash, model_id)
            validation_node_id = _make_node_id("validation", dhash, model_id)

            nodes = (
                EvidenceNodeDescriptor(
                    node_id=dataset_node_id,
                    node_type="dataset",
                    metadata={
                        "hash": dhash,
                        "feature_names": list(dataset.feature_names),
                        "label_name": dataset.label_name,
                        "sample_count": dataset.sample_count,
                        "feature_count": dataset.feature_count,
                    },
                ),
                EvidenceNodeDescriptor(
                    node_id=model_node_id,
                    node_type="model",
                    metadata={
                        "model_id": model_id,
                        "algorithm": model_type,
                        "version": model_version,
                        "dataset_hash": dhash,
                    },
                ),
                EvidenceNodeDescriptor(
                    node_id=validation_node_id,
                    node_type="validation",
                    metadata={
                        "hash": validation_hash_str,
                        "fold_count": validation.fold_count,
                        "train_size": validation.train_size,
                        "validation_size": validation.validation_size,
                        "test_size": validation.test_size,
                    },
                ),
            )

            edges = (
                EvidenceEdgeDescriptor(
                    edge_id=_make_edge_id(dataset_node_id, model_node_id, "trains"),
                    source_id=dataset_node_id,
                    target_id=model_node_id,
                    relationship="trains",
                    metadata={"model_id": model_id},
                ),
                EvidenceEdgeDescriptor(
                    edge_id=_make_edge_id(model_node_id, validation_node_id, "validated_by"),
                    source_id=model_node_id,
                    target_id=validation_node_id,
                    relationship="validated_by",
                    metadata={"model_id": model_id},
                ),
                EvidenceEdgeDescriptor(
                    edge_id=_make_edge_id(dataset_node_id, validation_node_id, "validated_on"),
                    source_id=dataset_node_id,
                    target_id=validation_node_id,
                    relationship="validated_on",
                    metadata={"model_id": model_id},
                ),
            )

            # Step 6: Build and return PipelineReport.
            return PipelineReport(
                pipeline_id=pipeline_id,
                status=PipelineStatus.COMPLETED,
                dataset_hash=dhash,
                feature_names=tuple(dataset.feature_names),
                label_name=dataset.label_name,
                sample_count=dataset.sample_count,
                feature_count=dataset.feature_count,
                validation=validation,
                training=training,
                model_contract=model_contract,
                nodes=nodes,
                edges=edges,
                metadata=dict(metadata or {}),
                created_at=created_at,
            )

        except Exception as exc:
            # Build a minimal failed report.  Every failed report is still a
            # fully-valid PipelineReport; construct all nested contracts with
            # fields that satisfy the locked-module validators.
            pipeline_id = _make_pipeline_id(
                close,
                high,
                low,
                volume,
                model_id,
                train_size,
                validation_size,
                step_size,
            )
            # Use ValidationResult constructor with defaults.
            failed_validation = ValidationResult(
                train_size=train_size,
                validation_size=validation_size,
                test_size=0,
                fold_count=0,
                fold_results=(),
                metrics={},
                metadata={},
            )
            # Resolve the model type defensively: an unknown model_type must
            # not crash the error path.
            try:
                resolved_type = TrainingModelType.from_value(model_type)
            except Exception:
                resolved_type = TrainingModelType.FEATURE_WEIGHT
            # Build a minimal training ModelContract for the failed training
            # result.  The training contract requires a non-empty label_name.
            empty_training_contract = TrainingModelContract(
                model_id=model_id,
                name=model_name or model_id,
                version=model_version,
                model_type=resolved_type,
                feature_names=(),
                label_name="unknown",
                parameters={},
                metadata={},
                created_at=created_at,
                training_hash="",
            )
            # TrainingResult requires a non-empty dataset_hash; use a
            # deterministic placeholder derived from the pipeline inputs.
            failed_dhash = hashlib.sha256(
                json.dumps(
                    {
                        "close_len": len(close),
                        "model_id": model_id,
                        "status": "failed",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            failed_training = TrainingResult(
                model=empty_training_contract,
                metrics={},
                dataset_hash=failed_dhash,
                n_samples=0,
                n_features=0,
                predictions=(),
                metadata={},
            )
            failed_registry_contract = RegistryModelContract(
                model_id=model_id,
                name=model_name or model_id,
                version=model_version,
                algorithm=model_type,
                feature_names=(),
                label_name="unknown",
                dataset_hash=failed_dhash,
                validation_hash=failed_dhash,
                parameters={},
                created_at=created_at,
                metadata={"status": "failed"},
            )
            return PipelineReport(
                pipeline_id=pipeline_id,
                status=PipelineStatus.FAILED,
                dataset_hash=failed_dhash,
                feature_names=(),
                label_name="unknown",
                sample_count=0,
                feature_count=0,
                validation=failed_validation,
                training=failed_training,
                model_contract=failed_registry_contract,
                nodes=(),
                edges=(),
                metadata={"error": str(exc)},
                created_at=created_at,
            )


__all__ = [
    "ResearchOrchestrator",
]
