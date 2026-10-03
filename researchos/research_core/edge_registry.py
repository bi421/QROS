"""Governed probability and edge definitions for research claims."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from researchos.probability.calibration import CalibrationResult
from researchos.probability.economic_cost import EconomicCostContext
from researchos.research_core.evidence import EvidenceArtifact, EvidenceKind
from researchos.research_core.multiple_testing import MultipleTestingResult


class EdgeState(str, Enum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    ELIGIBLE = "ELIGIBLE"


@dataclass(frozen=True)
class ProbabilityDefinition:
    """Machine-readable definition of what a reported probability means."""

    probability_id: str
    version: str
    event_definition: str
    denominator_definition: str
    horizon: str
    min_sample_size: int = 1

    def __post_init__(self) -> None:
        for name, value in (
            ("probability_id", self.probability_id),
            ("version", self.version),
            ("event_definition", self.event_definition),
            ("denominator_definition", self.denominator_definition),
            ("horizon", self.horizon),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.min_sample_size < 1:
            raise ValueError("min_sample_size must be >= 1")


@dataclass(frozen=True)
class EdgeDefinition:
    """A falsifiable edge contract with evidence-backed eligibility gates."""

    edge_id: str
    version: str
    outcome_definition: str
    null_definition: str
    minimum_effect_size: float
    minimum_sample_size: int
    requires_out_of_sample: bool = True
    requires_replication: bool = True
    requires_multiple_testing: bool = True
    requires_calibration: bool = True
    requires_economic_cost_context: bool = True
    probability: ProbabilityDefinition | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("edge_id", self.edge_id),
            ("version", self.version),
            ("outcome_definition", self.outcome_definition),
            ("null_definition", self.null_definition),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.minimum_sample_size < 1:
            raise ValueError("minimum_sample_size must be >= 1")

    def evaluate(
        self,
        *,
        sample_size: int,
        out_of_sample: bool,
        replicated: bool,
        observed_effect_size: float,
        uncertainty_lower_bound: float | None = None,
        out_of_sample_evidence_id: str | None = None,
        replication_evidence_id: str | None = None,
        out_of_sample_evidence: EvidenceArtifact | None = None,
        replication_evidence: EvidenceArtifact | None = None,
        multiple_testing_result: MultipleTestingResult | None = None,
        multiple_testing_hypothesis_index: int = 0,
        calibration_result: CalibrationResult | None = None,
        economic_cost_context: EconomicCostContext | None = None,
    ) -> tuple[EdgeState, tuple[str, ...]]:
        reasons: list[str] = []
        if sample_size < self.minimum_sample_size:
            reasons.append(f"insufficient_sample_size:{sample_size}<{self.minimum_sample_size}")
        if observed_effect_size < self.minimum_effect_size:
            reasons.append(
                f"effect_below_minimum:{observed_effect_size}<{self.minimum_effect_size}"
            )
        if uncertainty_lower_bound is None:
            reasons.append("uncertainty_required")
        elif uncertainty_lower_bound < self.minimum_effect_size:
            reasons.append(
                f"uncertainty_below_minimum:{uncertainty_lower_bound}<{self.minimum_effect_size}"
            )

        if self.requires_multiple_testing:
            if multiple_testing_result is None:
                reasons.append("multiple_testing_result_required")
            else:
                if not 0 <= multiple_testing_hypothesis_index < len(
                    multiple_testing_result.p_values
                ):
                    reasons.append("multiple_testing_hypothesis_index_invalid")
                elif not multiple_testing_result.reject()[
                    multiple_testing_hypothesis_index
                ]:
                    reasons.append("multiple_testing_not_rejected")

        if self.requires_calibration:
            if calibration_result is None:
                reasons.append("calibration_result_required")
            elif calibration_result.sample_size < self.minimum_sample_size:
                reasons.append(
                    f"calibration_sample_size_insufficient:{calibration_result.sample_size}<{self.minimum_sample_size}"
                )

        if self.requires_economic_cost_context:
            if economic_cost_context is None:
                reasons.append("economic_cost_context_required")
            else:
                total_cost = economic_cost_context.total_cost
                net_effect = economic_cost_context.net_effect(observed_effect_size)
                if total_cost > 0 and net_effect < self.minimum_effect_size:
                    reasons.append(
                        "net_effect_below_minimum:"
                        f"{net_effect}"
                        f"<{self.minimum_effect_size}"
                    )

        if self.requires_out_of_sample:
            if not out_of_sample:
                reasons.append("out_of_sample_required")
            if out_of_sample_evidence is None:
                reasons.append("out_of_sample_evidence_artifact_required")
            else:
                if (
                    out_of_sample_evidence_id
                    and out_of_sample_evidence.evidence_id != out_of_sample_evidence_id
                ):
                    reasons.append("out_of_sample_evidence_id_mismatch")
                if out_of_sample_evidence.kind is not EvidenceKind.OUT_OF_SAMPLE:
                    reasons.append("out_of_sample_evidence_kind_invalid")
                if out_of_sample_evidence.sample_size != sample_size:
                    reasons.append("out_of_sample_sample_size_mismatch")

        if self.requires_replication:
            if not replicated:
                reasons.append("replication_required")
            if replication_evidence is None:
                reasons.append("replication_evidence_artifact_required")
            else:
                if (
                    replication_evidence_id
                    and replication_evidence.evidence_id != replication_evidence_id
                ):
                    reasons.append("replication_evidence_id_mismatch")
                if replication_evidence.kind is not EvidenceKind.REPLICATION:
                    reasons.append("replication_evidence_kind_invalid")

        return (
            (EdgeState.NOT_ELIGIBLE, tuple(reasons))
            if reasons
            else (EdgeState.ELIGIBLE, ())
        )


@dataclass(frozen=True)
class EdgeDecision:
    edge_id: str
    version: str
    state: EdgeState
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class EdgeRegistrySnapshot:
    registry_version: str
    decisions: tuple[EdgeDecision, ...]
    registry_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        payload = {
            "registry_version": self.registry_version,
            "decisions": tuple(
                (d.edge_id, d.version, d.state.value, d.reasons)
                for d in self.decisions
            ),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        object.__setattr__(
            self, "registry_sha256", hashlib.sha256(encoded).hexdigest()
        )


class EdgeRegistry:
    """Deterministic registry of explicitly governed edge definitions."""

    registry_version = "edge-registry.v5"

    def __init__(self, definitions: Sequence[EdgeDefinition]) -> None:
        by_id: dict[str, EdgeDefinition] = {}
        for definition in definitions:
            if definition.edge_id in by_id:
                raise ValueError(f"duplicate edge_id: {definition.edge_id}")
            by_id[definition.edge_id] = definition
        self._definitions = by_id

    def definitions(self) -> tuple[EdgeDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

    def get(self, edge_id: str) -> EdgeDefinition:
        return self._definitions[edge_id]

    def evaluate(self, **kwargs: Any) -> EdgeRegistrySnapshot:
        decisions = tuple(
            EdgeDecision(
                definition.edge_id,
                definition.version,
                *definition.evaluate(**kwargs),
            )
            for definition in self.definitions()
        )
        return EdgeRegistrySnapshot(self.registry_version, decisions)


DEFAULT_EDGE_REGISTRY = EdgeRegistry(
    (
        EdgeDefinition(
            edge_id="edge.conditional_event_rate.v1",
            version="1",
            outcome_definition="P(event occurs | declared information set)",
            null_definition="event rate equals the pre-registered baseline rate",
            minimum_effect_size=0.0,
            minimum_sample_size=30,
            probability=ProbabilityDefinition(
                probability_id="prob.conditional_event_rate.v1",
                version="1",
                event_definition="declared binary outcome occurs within the registered horizon",
                denominator_definition="all eligible observations in the declared population",
                horizon="declared_by_analysis",
                min_sample_size=30,
            ),
        ),
    )
)


__all__ = [
    "DEFAULT_EDGE_REGISTRY",
    "EdgeDecision",
    "EdgeDefinition",
    "EdgeRegistry",
    "EdgeRegistrySnapshot",
    "EdgeState",
    "ProbabilityDefinition",
]
