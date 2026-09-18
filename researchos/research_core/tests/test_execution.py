from __future__ import annotations

import pytest

from researchos.quant_engine.backend import PythonQuantBackend
from researchos.research_core.execution import (
    ExecutionBinding,
    ExecutionRegistry,
    registry_for_backend,
    validate_backend_capability,
)


def test_execution_registry_requires_binding_for_every_selected_method() -> None:
    registry = ExecutionRegistry(
        (
            ExecutionBinding(
                method_id="quant.calculate_statistics.v1",
                method_version="1",
                operation="calculate_statistics",
                backend="PythonQuantBackend",
                backend_version="1.0.0",
            ),
        )
    )
    registry.verify_plan(("quant.calculate_statistics.v1",))
    with pytest.raises(ValueError, match="without executable bindings"):
        registry.verify_plan(("quant.calculate_statistics.v1", "missing.v1"))


def test_binding_rejects_nondeterministic_execution() -> None:
    with pytest.raises(ValueError, match="deterministic"):
        ExecutionBinding(
            method_id="x",
            method_version="1",
            operation="calculate_statistics",
            backend="python",
            backend_version="1",
            deterministic=False,
        )


def test_backend_capability_gate_checks_operation_and_trust_guarantees() -> None:
    binding = ExecutionBinding(
        method_id="quant.calculate_statistics.v1",
        method_version="1",
        operation="calculate_statistics",
        backend="PythonQuantBackend",
        backend_version="1.0.0",
    )
    capabilities = {
        "deterministic": True,
        "no_randomness": True,
        "supported_operations": ("calculate_statistics",),
    }
    validate_backend_capability(binding, capabilities)
    with pytest.raises(ValueError, match="does not support operation"):
        validate_backend_capability(
            binding,
            {**capabilities, "supported_operations": ()},
        )


def test_registry_is_derived_from_real_python_backend_capabilities() -> None:
    registry = registry_for_backend(PythonQuantBackend())
    methods = {binding.method_id for binding in registry.bindings()}
    assert methods == {
        "quant.calculate_returns.v1",
        "quant.calculate_volatility.v1",
        "quant.calculate_drawdown.v1",
        "quant.calculate_statistics.v1",
        "quant.calculate_metrics.v1",
        "quant.calculate_performance_analytics.v1",
    }
    binding = registry.get("quant.calculate_statistics.v1")
    assert binding.operation == "calculate_statistics"
    assert binding.backend == "PythonQuantBackend"
    assert binding.backend_version == "1.0.0"
