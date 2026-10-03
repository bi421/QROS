"""Provider-neutral model execution boundary.

This module owns executable adapter lifecycle and dispatch only.
It does not train models, execute trading, fabricate probabilities, or create
research evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

MODEL_RUNTIME_VERSION = "1.0.0"


class ModelRuntimeError(RuntimeError):
    """Base class for model runtime failures."""


class ModelAdapterAlreadyExistsError(ModelRuntimeError):
    """Raised when an adapter id is already registered."""

    def __init__(self, model_id: str) -> None:
        super().__init__(f"model adapter already registered: {model_id!r}")
        self.model_id = model_id


class ModelAdapterNotFoundError(ModelRuntimeError):
    """Raised when an adapter id is unknown."""

    def __init__(self, model_id: str) -> None:
        super().__init__(f"model adapter not found: {model_id!r}")
        self.model_id = model_id


class ModelNotReadyError(ModelRuntimeError):
    """Raised when inference is attempted before explicit readiness."""

    def __init__(self, model_id: str) -> None:
        super().__init__(f"model adapter is not ready: {model_id!r}")
        self.model_id = model_id


class ModelResultMismatchError(ModelRuntimeError):
    """Raised when an adapter returns mismatched execution identity."""

    def __init__(self, field: str, expected: str, actual: str) -> None:
        super().__init__(
            f"model result {field} mismatch: expected {expected!r}, got {actual!r}"
        )
        self.field = field
        self.expected = expected
        self.actual = actual


class BatchResultCountMismatchError(ModelRuntimeError):
    """Raised when batch output count does not match input count."""

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(
            f"batch result count mismatch: expected {expected}, got {actual}"
        )
        self.expected = expected
        self.actual = actual


def _freeze_parameters(parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Copy runtime parameters into a read-only mapping."""
    return MappingProxyType(dict(parameters))


@dataclass(frozen=True)
class InferenceRequest:
    """Immutable execution envelope passed to a model adapter."""

    dataset_hash: str
    window_start: str
    window_end: str
    input_schema: tuple[str, ...]
    payload: Any
    parameters: Mapping[str, Any] = field(default_factory=dict)
    seed: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_hash, str) or not self.dataset_hash.strip():
            raise ValueError("dataset_hash must be a non-empty string")
        if not isinstance(self.window_start, str) or not self.window_start.strip():
            raise ValueError("window_start must be a non-empty string")
        if not isinstance(self.window_end, str) or not self.window_end.strip():
            raise ValueError("window_end must be a non-empty string")
        object.__setattr__(self, "input_schema", tuple(self.input_schema))
        object.__setattr__(
            self,
            "parameters",
            _freeze_parameters(self.parameters),
        )


@dataclass(frozen=True)
class InferenceResult:
    """Immutable adapter output envelope.

    Predictions intentionally remain model-native. Probability conversion and
    calibration belong to downstream research services.
    """

    model_id: str
    model_version: str
    dataset_hash: str
    predictions: Any
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id must be a non-empty string")
        if not isinstance(self.model_version, str) or not self.model_version.strip():
            raise ValueError("model_version must be a non-empty string")
        if not isinstance(self.dataset_hash, str) or not self.dataset_hash.strip():
            raise ValueError("dataset_hash must be a non-empty string")
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )


@runtime_checkable
class ModelAdapter(Protocol):
    """Executable model contract with explicit lifecycle."""

    @property
    def model_id(self) -> str:
        ...

    @property
    def model_version(self) -> str:
        ...

    def load(self) -> None:
        ...

    def unload(self) -> None:
        ...

    def is_ready(self) -> bool:
        ...

    def predict(self, request: InferenceRequest) -> InferenceResult:
        ...

    def predict_batch(
        self, requests: Sequence[InferenceRequest]
    ) -> Sequence[InferenceResult]:
        ...


class ModelRuntime:
    """Explicit, process-local runtime for executable model adapters.

    The runtime deliberately has no implicit loading, switching, or fallback.
    Each instance owns its own adapter mapping and can therefore be constructed
    independently by workers and tests.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, ModelAdapter] = {}

    def register(self, adapter: ModelAdapter) -> None:
        """Register one executable adapter."""
        if not isinstance(adapter, ModelAdapter):
            raise TypeError("register() expects a ModelAdapter")
        model_id = adapter.model_id
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("adapter.model_id must be a non-empty string")
        if model_id in self._adapters:
            raise ModelAdapterAlreadyExistsError(model_id)
        self._adapters[model_id] = adapter

    def get(self, model_id: str) -> ModelAdapter:
        """Return the registered adapter for model_id."""
        try:
            return self._adapters[model_id]
        except KeyError:
            raise ModelAdapterNotFoundError(model_id) from None

    def list_models(self) -> tuple[str, ...]:
        """Return registered ids in deterministic order."""
        return tuple(sorted(self._adapters))

    def load(self, model_id: str) -> None:
        """Explicitly load one adapter."""
        self.get(model_id).load()

    def unload(self, model_id: str) -> None:
        """Explicitly unload one adapter."""
        self.get(model_id).unload()

    def is_ready(self, model_id: str) -> bool:
        """Return adapter readiness without changing state."""
        return self.get(model_id).is_ready()

    def predict(
        self, model_id: str, request: InferenceRequest
    ) -> InferenceResult:
        """Dispatch one inference request after an explicit readiness check."""
        adapter = self.get(model_id)
        self._require_ready(adapter)
        result = adapter.predict(request)
        self._validate_result(adapter, request, result)
        return result

    def predict_batch(
        self, model_id: str, requests: Sequence[InferenceRequest]
    ) -> tuple[InferenceResult, ...]:
        """Dispatch a batch while preserving request/result cardinality."""
        adapter = self.get(model_id)
        self._require_ready(adapter)
        request_tuple = tuple(requests)
        results = tuple(adapter.predict_batch(request_tuple))
        if len(results) != len(request_tuple):
            raise BatchResultCountMismatchError(len(request_tuple), len(results))
        for request, result in zip(request_tuple, results):
            self._validate_result(adapter, request, result)
        return results

    @staticmethod
    def _require_ready(adapter: ModelAdapter) -> None:
        if not adapter.is_ready():
            raise ModelNotReadyError(adapter.model_id)

    @staticmethod
    def _validate_result(
        adapter: ModelAdapter,
        request: InferenceRequest,
        result: InferenceResult,
    ) -> None:
        if not isinstance(result, InferenceResult):
            raise TypeError("adapter must return an InferenceResult")
        if result.model_id != adapter.model_id:
            raise ModelResultMismatchError(
                "model_id", adapter.model_id, result.model_id
            )
        if result.model_version != adapter.model_version:
            raise ModelResultMismatchError(
                "model_version", adapter.model_version, result.model_version
            )
        if result.dataset_hash != request.dataset_hash:
            raise ModelResultMismatchError(
                "dataset_hash", request.dataset_hash, result.dataset_hash
            )


__all__ = [
    "MODEL_RUNTIME_VERSION",
    "BatchResultCountMismatchError",
    "InferenceRequest",
    "InferenceResult",
    "ModelAdapter",
    "ModelAdapterAlreadyExistsError",
    "ModelAdapterNotFoundError",
    "ModelNotReadyError",
    "ModelResultMismatchError",
    "ModelRuntime",
    "ModelRuntimeError",
]
