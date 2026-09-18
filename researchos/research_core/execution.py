"""Governed binding between a planned method and an executable backend operation.

The binding layer prevents the planner from becoming a symbolic-only registry:
every executable method must declare the operation it maps to, the backend
identity, and the trust guarantees required before execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


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


def validate_backend_capability(
    binding: ExecutionBinding,
    backend_capabilities: Mapping[str, object],
) -> None:
    """Validate the minimum trust guarantees required by a binding."""
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


__all__ = ["ExecutionBinding", "ExecutionRegistry", "validate_backend_capability"]
