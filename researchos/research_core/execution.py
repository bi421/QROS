"""Governed binding between planned methods and executable QROS backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from researchos.quant_engine.interface import QuantComputationInterface


@dataclass(frozen=True)
class ExecutionBinding:
    method_id: str
    method_version: str
    operation: str
    backend: str
    backend_version: str
    deterministic: bool = True
    requires_no_randomness: bool = True

    def __post_init__(self) -> None:
        for name, value in (
            ("method_id", self.method_id),
            ("method_version", self.method_version),
            ("operation", self.operation),
            ("backend", self.backend),
            ("backend_version", self.backend_version),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not self.deterministic:
            raise ValueError("research execution requires deterministic bindings")
        if not self.requires_no_randomness:
            raise ValueError("research execution bindings must forbid randomness")


class ExecutionRegistry:
    """Deterministic registry of executable method bindings."""

    def __init__(self, bindings: tuple[ExecutionBinding, ...]) -> None:
        by_method: dict[str, ExecutionBinding] = {}
        for binding in bindings:
            if binding.method_id in by_method:
                raise ValueError(f"duplicate execution binding: {binding.method_id}")
            by_method[binding.method_id] = binding
        self._bindings = by_method

    def get(self, method_id: str) -> ExecutionBinding:
        try:
            return self._bindings[method_id]
        except KeyError as exc:
            raise KeyError(f"no executable binding for method: {method_id}") from exc

    def bindings(self) -> tuple[ExecutionBinding, ...]:
        return tuple(self._bindings[key] for key in sorted(self._bindings))

    def verify_plan(self, selected_methods: tuple[str, ...]) -> None:
        missing = sorted(set(selected_methods) - self._bindings.keys())
        if missing:
            raise ValueError(
                "compute plan contains methods without executable bindings: "
                + ",".join(missing)
            )


def registry_for_backend(
    backend: QuantComputationInterface,
    method_versions: Mapping[str, str] | None = None,
) -> ExecutionRegistry:
    """Derive executable research methods from a certified backend surface."""
    capabilities = backend.capabilities()
    versions = method_versions or {}
    operation_to_method = {
        "calculate_returns": "quant.calculate_returns.v1",
        "calculate_volatility": "quant.calculate_volatility.v1",
        "calculate_drawdown": "quant.calculate_drawdown.v1",
        "calculate_statistics": "quant.calculate_statistics.v1",
        "calculate_metrics": "quant.calculate_metrics.v1",
        "calculate_performance_analytics": "quant.calculate_performance_analytics.v1",
    }
    bindings = tuple(
        ExecutionBinding(
            method_id=method_id,
            method_version=versions.get(method_id, "1"),
            operation=operation,
            backend=capabilities.backend_name,
            backend_version=capabilities.version,
            deterministic=capabilities.deterministic,
            requires_no_randomness=capabilities.no_randomness,
        )
        for operation, method_id in operation_to_method.items()
        if capabilities.supports(operation)
    )
    return ExecutionRegistry(bindings)


def validate_backend_capability(
    binding: ExecutionBinding,
    backend_capabilities: Mapping[str, object],
) -> None:
    """Validate the trust guarantees required by an execution binding."""
    if not bool(backend_capabilities.get("deterministic", False)):
        raise ValueError(f"backend is not deterministic: {binding.backend}")
    if binding.requires_no_randomness and not bool(
        backend_capabilities.get("no_randomness", False)
    ):
        raise ValueError(f"backend permits randomness: {binding.backend}")
    supported = backend_capabilities.get("supported_operations", ())
    if binding.operation not in supported:
        raise ValueError(
            f"backend does not support operation {binding.operation}: {binding.backend}"
        )


__all__ = [
    "ExecutionBinding",
    "ExecutionRegistry",
    "registry_for_backend",
    "validate_backend_capability",
]
