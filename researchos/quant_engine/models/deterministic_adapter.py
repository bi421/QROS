"""Concrete adapter for QROS deterministic research-model contracts.

This adapter connects the registry contract to the existing deterministic
training executor through the provider-neutral model execution boundary.
It owns no evidence, tenant state, or trading decisions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ..machine_learning.dataset_contracts import ResearchDataset
from ..training.contracts import ModelContract as TrainingModelContract
from ..training.contracts import ModelType
from ..training.trainer import Trainer, dataset_hash, validate_dataset
from .contracts import ModelContract
from .runtime import InferenceRequest, InferenceResult


@dataclass
class DeterministicResearchModelAdapter:
    """Execute one immutable deterministic registry model contract."""

    model: ModelContract
    trainer: Trainer = field(default_factory=Trainer)
    _ready: bool = field(default=False, init=False, repr=False)
    _training_model: TrainingModelContract = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Build the execution contract from the canonical registry contract."""
        try:
            model_type = ModelType.from_value(self.model.algorithm)
        except ValueError as exc:
            raise ValueError(
                "unsupported deterministic model algorithm: "
                f"{self.model.algorithm!r}"
            ) from exc

        object.__setattr__(
            self,
            "_training_model",
            TrainingModelContract(
                model_id=self.model.model_id,
                name=self.model.name,
                version=self.model.version,
                model_type=model_type,
                feature_names=tuple(self.model.feature_names),
                label_name=self.model.label_name,
                parameters=dict(self.model.parameters),
                metadata=dict(self.model.metadata),
                created_at=self.model.created_at,
                training_hash=str(self.model.metadata.get("training_hash", "")),
            ),
        )

    @property
    def model_id(self) -> str:
        """Return the immutable model identifier."""
        return self.model.model_id

    @property
    def model_version(self) -> str:
        """Return the immutable model version."""
        return self.model.version

    def load(self) -> None:
        """Mark the adapter ready for execution."""
        self._ready = True

    def unload(self) -> None:
        """Mark the adapter unavailable for execution."""
        self._ready = False

    def is_ready(self) -> bool:
        """Return current readiness without mutating state."""
        return self._ready

    def predict(self, request: InferenceRequest) -> InferenceResult:
        """Execute the bound deterministic model against one exact dataset."""
        dataset = request.payload
        if not isinstance(dataset, ResearchDataset):
            raise TypeError("request.payload must be a ResearchDataset")

        if request.parameters:
            raise ValueError(
                "request.parameters must be empty for a bound deterministic model"
            )
        if request.seed is not None:
            raise ValueError("request.seed must be None for a deterministic model")

        validate_dataset(dataset)
        actual_hash = dataset_hash(dataset)
        if actual_hash != request.dataset_hash:
            raise ValueError(
                "request.dataset_hash does not match the payload dataset hash"
            )
        if tuple(request.input_schema) != tuple(self.model.feature_names):
            raise ValueError("request.input_schema does not match the model contract")
        if tuple(dataset.feature_names) != tuple(self.model.feature_names):
            raise ValueError("dataset feature schema does not match the model contract")
        if dataset.label_name != self.model.label_name:
            raise ValueError("dataset label_name does not match the model contract")

        predictions = tuple(self.trainer.predict(self._training_model, dataset))
        return InferenceResult(
            model_id=self.model_id,
            model_version=self.model_version,
            dataset_hash=actual_hash,
            predictions=predictions,
            metadata={
                "algorithm": self.model.algorithm,
                "feature_names": tuple(self.model.feature_names),
                "prediction_count": len(predictions),
                "validation_hash": self.model.validation_hash,
                "model_contract_hash": self.model.content_hash(),
            },
        )

    def predict_batch(
        self, requests: Sequence[InferenceRequest]
    ) -> Sequence[InferenceResult]:
        """Execute each request in order through the same guarded path."""
        return tuple(self.predict(request) for request in requests)


__all__ = ["DeterministicResearchModelAdapter"]
