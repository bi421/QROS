"""
Model Registry — deterministic model lifecycle registry.

The registry stores model identity, metadata, configuration, and validation
history only.  It never trains models and never executes trading.

Architecture:

    ResearchDataset
            ↓
    ValidationResult
            ↓
    ModelContract
            ↓
    ModelRegistry
            ↓
    Experiment Engine
"""

from .contracts import (
    MODEL_CONTRACT_VERSION,
    ModelContract,
    ModelContractError,
)

# Backward-compatible re-export of the legacy quant-engine model contracts
# that previously lived in ``researchos/quant_engine/models.py``.  Every name
# is preserved verbatim so existing importers keep working unchanged.
from .legacy_models import (  # noqa: F401
    CalculationVersion,
    Order,
    OrderFill,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Signal,
    SimulationRequest,
    SimulationResult,
    Trade,
    periods_per_year_from_timeframe,
)
from .metadata import (
    MODEL_METADATA_VERSION,
    ModelMetadata,
)
from .runtime import (
    MODEL_RUNTIME_VERSION,
    BatchResultCountMismatchError,
    InferenceRequest,
    InferenceResult,
    ModelAdapter,
    ModelAdapterAlreadyExistsError,
    ModelAdapterNotFoundError,
    ModelNotReadyError,
    ModelResultMismatchError,
    ModelRuntime,
    ModelRuntimeError,
)
from .deterministic_adapter import DeterministicResearchModelAdapter
from .registry import (
    MODEL_REGISTRY_VERSION,
    ModelAlreadyExistsError,
    ModelNotFoundError,
    ModelRegistry,
    ModelRegistryError,
)

__all__ = [
    # Registry infrastructure
    "MODEL_CONTRACT_VERSION",
    "MODEL_METADATA_VERSION",
    "MODEL_REGISTRY_VERSION",
    "ModelContract",
    "ModelContractError",
    "ModelMetadata",
    "ModelRegistry",
    "ModelAlreadyExistsError",
    "ModelNotFoundError",
    "ModelRegistryError",
    # Executable model runtime
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
    "DeterministicResearchModelAdapter",
    # Legacy quant-engine models (backward-compatible re-exports)
    "CalculationVersion",
    "Order",
    "OrderFill",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "Signal",
    "SimulationRequest",
    "SimulationResult",
    "Trade",
    "periods_per_year_from_timeframe",
]