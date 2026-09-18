"""Deterministic research-method selection and computational planning.

This module is deliberately rule-based. It does not predict which method will
produce a desirable result; it selects only methods whose declared prerequisites
are satisfied by the supplied research context.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence


class Decision(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


class Backend(str, Enum):
    PYTHON = "python"
    CPP = "cpp"


@dataclass(frozen=True)
class ResearchContext:
    """Facts available to the planner before computation begins."""

    analysis_class: str
    sample_size: int
    feature_names: frozenset[str] = frozenset()
    has_time_order: bool = False
    has_serial_dependence: bool = False
    out_of_sample: bool = False
    post_hoc: bool = False
    multiple_testing_count: int = 1
    dataset_sha256: str = ""
    dataset_id: str = ""

    def __post_init__(self) -> None:
        if not self.analysis_class.strip():
            raise ValueError("analysis_class must not be empty")
        if self.sample_size < 0:
            raise ValueError("sample_size must be non-negative")
        if self.multiple_testing_count < 1:
            raise ValueError("multiple_testing_count must be >= 1")


@dataclass(frozen=True)
class ResearchMethod:
    """Machine-readable declaration of one governed quantitative method."""

    method_id: str
    version: str
    analysis_classes: frozenset[str]
    required_features: frozenset[str] = frozenset()
    min_sample_size: int = 1
    requires_time_order: bool = False
    requires_serial_dependence: bool = False
    requires_out_of_sample: bool = False
    forbids_post_hoc: bool = False
    backend: Backend = Backend.PYTHON
    deterministic: bool = True
    estimated_cost: int = 1

    def __post_init__(self) -> None:
        if not self.method_id.strip() or not self.version.strip():
            raise ValueError("method_id and version must not be empty")
        if not self.analysis_classes:
            raise ValueError("analysis_classes must not be empty")
        if self.min_sample_size < 1:
            raise ValueError("min_sample_size must be >= 1")
        if self.estimated_cost < 1:
            raise ValueError("estimated_cost must be >= 1")

    def evaluate(self, context: ResearchContext) -> tuple[Decision, tuple[str, ...]]:
        reasons: list[str] = []
        if context.analysis_class not in self.analysis_classes:
            reasons.append("analysis_class_not_supported")
        missing = sorted(self.required_features - context.feature_names)
        if missing:
            reasons.append("missing_features:" + ",".join(missing))
        if context.sample_size < self.min_sample_size:
            reasons.append(f"insufficient_sample_size:{context.sample_size}<{self.min_sample_size}")
        if self.requires_time_order and not context.has_time_order:
            reasons.append("time_order_required")
        if self.requires_serial_dependence and not context.has_serial_dependence:
            reasons.append("serial_dependence_required")
        if self.requires_out_of_sample and not context.out_of_sample:
            reasons.append("out_of_sample_required")
        if self.forbids_post_hoc and context.post_hoc:
            reasons.append("post_hoc_not_allowed")
        return (Decision.NOT_ELIGIBLE, tuple(reasons)) if reasons else (Decision.ELIGIBLE, ())


@dataclass(frozen=True)
class MethodDecision:
    method_id: str
    version: str
    decision: Decision
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ComputePlan:
    """Immutable, content-addressed computational route selected by the planner."""

    plan_version: str
    dataset_id: str
    dataset_sha256: str
    analysis_class: str
    selected_methods: tuple[str, ...]
    backend_by_method: tuple[tuple[str, str], ...]
    selection_reasons: tuple[str, ...]
    rejected_methods: tuple[MethodDecision, ...]
    plan_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        payload = {
            "plan_version": self.plan_version,
            "dataset_id": self.dataset_id,
            "dataset_sha256": self.dataset_sha256,
            "analysis_class": self.analysis_class,
            "selected_methods": self.selected_methods,
            "backend_by_method": self.backend_by_method,
            "selection_reasons": self.selection_reasons,
            "rejected_methods": tuple(
                (d.method_id, d.version, d.decision.value, d.reasons)
                for d in self.rejected_methods
            ),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        object.__setattr__(self, "plan_sha256", hashlib.sha256(encoded).hexdigest())


@dataclass(frozen=True)
class ValidationPlan:
    """Deterministic safety checks required before a result is consumable."""

    checks: tuple[str, ...] = (
        "dataset_integrity",
        "method_prerequisites",
        "no_lookahead_leakage",
        "result_provenance",
        "reproducibility",
    )


class CapabilityRegistry:
    """Immutable-style registry of governed methods."""

    def __init__(self, methods: Sequence[ResearchMethod]) -> None:
        by_id: dict[str, ResearchMethod] = {}
        for method in methods:
            if method.method_id in by_id:
                raise ValueError(f"duplicate method_id: {method.method_id}")
            by_id[method.method_id] = method
        self._methods = by_id

    def methods(self) -> tuple[ResearchMethod, ...]:
        return tuple(self._methods[key] for key in sorted(self._methods))

    def get(self, method_id: str) -> ResearchMethod:
        return self._methods[method_id]


DEFAULT_CAPABILITIES = CapabilityRegistry(
    (
        ResearchMethod(
            "probability.wilson.v1",
            "1",
            frozenset({"probability", "binary_outcome"}),
            min_sample_size=1,
        ),
        ResearchMethod(
            "dependence.block_bootstrap.v1",
            "1",
            frozenset({"dependence", "time_series"}),
            min_sample_size=30,
            requires_time_order=True,
            requires_serial_dependence=True,
        ),
        ResearchMethod(
            "information.mutual_information.v1",
            "1",
            frozenset({"feature_information"}),
            required_features=frozenset({"feature", "target"}),
            min_sample_size=30,
        ),
        ResearchMethod(
            "risk.expected_shortfall.v1",
            "1",
            frozenset({"tail_risk", "risk"}),
            min_sample_size=30,
        ),
    )
)


class ResearchPlanner:
    """Select the minimum sufficient set of eligible methods deterministically."""

    plan_version = "research-planner.v1"

    def __init__(self, registry: CapabilityRegistry = DEFAULT_CAPABILITIES) -> None:
        self._registry = registry

    def plan(self, context: ResearchContext) -> tuple[ComputePlan, ValidationPlan]:
        decisions = tuple(
            MethodDecision(
                method.method_id,
                method.version,
                *method.evaluate(context),
            )
            for method in self._registry.methods()
        )
        eligible = tuple(
            decision for decision in decisions if decision.decision is Decision.ELIGIBLE
        )
        if not eligible:
            raise ValueError(
                "no eligible computational method: "
                + "; ".join(
                    f"{d.method_id}={','.join(d.reasons)}"
                    for d in decisions
                )
            )

        selected = tuple(d.method_id for d in eligible)
        backend = tuple(
            (d.method_id, self._registry.get(d.method_id).backend.value)
            for d in eligible
        )
        reasons = tuple(
            f"selected:{d.method_id}:prerequisites_satisfied"
            for d in eligible
        )
        plan = ComputePlan(
            plan_version=self.plan_version,
            dataset_id=context.dataset_id,
            dataset_sha256=context.dataset_sha256,
            analysis_class=context.analysis_class,
            selected_methods=selected,
            backend_by_method=backend,
            selection_reasons=reasons,
            rejected_methods=tuple(
                d for d in decisions if d.decision is Decision.NOT_ELIGIBLE
            ),
        )
        checks = list(ValidationPlan().checks)
        if context.multiple_testing_count > 1:
            checks.append("multiple_testing_control")
        if context.post_hoc:
            checks.append("post_hoc_label")
        if context.out_of_sample:
            checks.append("out_of_sample_integrity")
        return plan, ValidationPlan(tuple(checks))


__all__ = [
    "Backend",
    "CapabilityRegistry",
    "ComputePlan",
    "DEFAULT_CAPABILITIES",
    "Decision",
    "MethodDecision",
    "ResearchContext",
    "ResearchMethod",
    "ResearchPlanner",
    "ValidationPlan",
]
