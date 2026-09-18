"""Immutable, provenance-complete result contract for governed quantitative analyses."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from researchos.research_core.contracts import _validate_sha256
from researchos.research_core.intelligence import ComputePlan


class AnalysisState(str, Enum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    ELIGIBLE = "ELIGIBLE"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    VALIDATED = "VALIDATED"
    CONSUMABLE = "CONSUMABLE"
    FAILED = "FAILED"
    INVALID = "INVALID"
    CONTRADICTED = "CONTRADICTED"
    SUPERSEDED = "SUPERSEDED"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash_payload(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AnalysisResult:
    """Universal immutable result envelope required by the 2026 execution contract."""

    analysis_id: str
    claim_id: str
    analysis_class: str
    population_definition: str
    time_window: str
    data_version: str
    data_hash: str
    feature_version: str
    label_version: str
    method: str
    model_version: str
    assumptions: tuple[str, ...]
    sample_size: int
    effective_sample_size: float | None
    point_estimate: Any
    uncertainty_interval: tuple[float, float] | None
    probability_definition: str
    effect_size: Any
    diagnostics: tuple[tuple[str, Any], ...]
    warnings: tuple[str, ...]
    multiple_testing_context: tuple[tuple[str, Any], ...]
    selection_count: int
    integrity_gate_status: str
    out_of_sample_status: str
    replication_status: str
    calibration_status: str
    economic_cost_model: str
    result_artifact_hash: str
    state: AnalysisState = AnalysisState.COMPLETED
    plan_sha256: str = ""

    def __post_init__(self) -> None:
        for name, value in (
            ("analysis_id", self.analysis_id),
            ("claim_id", self.claim_id),
            ("analysis_class", self.analysis_class),
            ("population_definition", self.population_definition),
            ("time_window", self.time_window),
            ("data_version", self.data_version),
            ("feature_version", self.feature_version),
            ("label_version", self.label_version),
            ("method", self.method),
            ("model_version", self.model_version),
            ("probability_definition", self.probability_definition),
            ("economic_cost_model", self.economic_cost_model),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        object.__setattr__(self, "data_hash", _validate_sha256(self.data_hash, "data_hash"))
        object.__setattr__(
            self,
            "result_artifact_hash",
            _validate_sha256(self.result_artifact_hash, "result_artifact_hash"),
        )
        if self.plan_sha256:
            object.__setattr__(self, "plan_sha256", _validate_sha256(self.plan_sha256, "plan_sha256"))
        if self.sample_size < 0:
            raise ValueError("sample_size must be non-negative")
        if self.effective_sample_size is not None and self.effective_sample_size < 0:
            raise ValueError("effective_sample_size must be non-negative")
        if self.selection_count < 1:
            raise ValueError("selection_count must be >= 1")
        if self.uncertainty_interval is not None:
            low, high = self.uncertainty_interval
            if low > high:
                raise ValueError("uncertainty_interval lower bound must not exceed upper bound")
        if self.state in {AnalysisState.VALIDATED, AnalysisState.CONSUMABLE}:
            if self.integrity_gate_status != "PASS":
                raise ValueError("validated/consumable results require integrity_gate_status=PASS")
        if self.state is AnalysisState.CONSUMABLE:
            if self.out_of_sample_status not in {"PASS", "NOT_APPLICABLE"}:
                raise ValueError("consumable results require an acceptable out_of_sample_status")
            if self.replication_status not in {"PASS", "NOT_APPLICABLE"}:
                raise ValueError("consumable results require replication or explicit NOT_APPLICABLE")

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "analysis_id": self.analysis_id,
            "claim_id": self.claim_id,
            "analysis_class": self.analysis_class,
            "population_definition": self.population_definition,
            "time_window": self.time_window,
            "data_version": self.data_version,
            "data_hash": self.data_hash,
            "feature_version": self.feature_version,
            "label_version": self.label_version,
            "method": self.method,
            "model_version": self.model_version,
            "assumptions": list(self.assumptions),
            "sample_size": self.sample_size,
            "effective_sample_size": self.effective_sample_size,
            "point_estimate": self.point_estimate,
            "uncertainty_interval": self.uncertainty_interval,
            "probability_definition": self.probability_definition,
            "effect_size": self.effect_size,
            "diagnostics": list(self.diagnostics),
            "warnings": list(self.warnings),
            "multiple_testing_context": list(self.multiple_testing_context),
            "selection_count": self.selection_count,
            "integrity_gate_status": self.integrity_gate_status,
            "out_of_sample_status": self.out_of_sample_status,
            "replication_status": self.replication_status,
            "calibration_status": self.calibration_status,
            "economic_cost_model": self.economic_cost_model,
            "result_artifact_hash": self.result_artifact_hash,
            "state": self.state.value,
            "plan_sha256": self.plan_sha256,
        }

    @property
    def result_sha256(self) -> str:
        """Deterministic identity of the complete governed result envelope."""
        return _hash_payload(self.canonical_payload)

    @classmethod
    def from_plan(
        cls,
        plan: ComputePlan,
        *,
        analysis_id: str,
        claim_id: str,
        population_definition: str,
        time_window: str,
        data_version: str,
        feature_version: str,
        label_version: str,
        point_estimate: Any,
        uncertainty_interval: tuple[float, float] | None,
        probability_definition: str,
        effect_size: Any,
        result_artifact_hash: str,
        assumptions: Sequence[str] = (),
        diagnostics: Mapping[str, Any] | None = None,
        warnings: Sequence[str] = (),
        multiple_testing_context: Mapping[str, Any] | None = None,
        sample_size: int = 0,
        effective_sample_size: float | None = None,
        integrity_gate_status: str = "PASS",
        out_of_sample_status: str = "NOT_APPLICABLE",
        replication_status: str = "NOT_APPLICABLE",
        calibration_status: str = "NOT_APPLICABLE",
        economic_cost_model: str = "UNSPECIFIED",
        state: AnalysisState = AnalysisState.COMPLETED,
    ) -> "AnalysisResult":
        """Bind a computed result to exactly one immutable planner output."""
        if len(plan.selected_methods) != 1:
            raise ValueError(
                "AnalysisResult.from_plan requires exactly one selected method; "
                "compose multi-method analyses at a higher orchestration layer"
            )
        return cls(
            analysis_id=analysis_id,
            claim_id=claim_id,
            analysis_class=plan.analysis_class,
            population_definition=population_definition,
            time_window=time_window,
            data_version=data_version,
            data_hash=plan.dataset_sha256,
            feature_version=feature_version,
            label_version=label_version,
            method=plan.selected_methods[0],
            model_version=plan.plan_version,
            assumptions=tuple(assumptions),
            sample_size=sample_size,
            effective_sample_size=effective_sample_size,
            point_estimate=point_estimate,
            uncertainty_interval=uncertainty_interval,
            probability_definition=probability_definition,
            effect_size=effect_size,
            diagnostics=tuple(sorted((diagnostics or {}).items())),
            warnings=tuple(warnings),
            multiple_testing_context=tuple(sorted((multiple_testing_context or {}).items())),
            selection_count=1,
            integrity_gate_status=integrity_gate_status,
            out_of_sample_status=out_of_sample_status,
            replication_status=replication_status,
            calibration_status=calibration_status,
            economic_cost_model=economic_cost_model,
            result_artifact_hash=result_artifact_hash,
            state=state,
            plan_sha256=plan.plan_sha256,
        )


__all__ = ["AnalysisResult", "AnalysisState"]
