"""Governed probability and edge definitions for research claims.

Definitions are descriptive contracts, not predictive models. A registry may
select a definition only when its declared prerequisites are satisfied.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


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
    """A falsifiable edge contract with explicit eligibility requirements."""

    edge_id: str
    version: str
    outcome_definition: str
    null_definition: str
    minimum_effect_size: float
    minimum_sample_size: int
    requires_out_of_sample: bool = True
    requires_replication: bool = True
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
    ) -> tuple[EdgeState, tuple[str, ...]]:
        reasons: list[str] = []
        if sample_size < self.minimum_sample_size:
            reasons.append(f"insufficient_sample_size:{sample_size}<{self.minimum_sample_size}")
        if observed_effect_size < self.minimum_effect_size:
            reasons.append(f"effect_below_minimum:{observed_effect_size}<{self.minimum_effect_size}")
        if uncertainty_lower_bound is None:
            reasons.append("uncertainty_required")
        elif uncertainty_lower_bound < self.minimum_effect_size:
            reasons.append(f"uncertainty_below_minimum:{uncertainty_lower_bound}<{self.minimum_effect_size}")
        if self.requires_out_of_sample and not out_of_sample:
            reasons.append("out_of_sample_required")
        if self.requires_out_of_sample and not out_of_sample_evidence_id:
            reasons.append("out_of_sample_evidence_required")
        if self.requires_replication and not replicated:
            reasons.append("replication_required")
        if self.requires_replication and not replication_evidence_id:
            reasons.append("replication_evidence_required")
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
    """Deterministic content identity of the registered edge definitions."""

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
            self,
            "registry_sha256",
            hashlib.sha256(encoded).hexdigest(),
        )


class EdgeRegistry:
    """Deterministic registry of explicitly governed edge definitions."""

    registry_version = "edge-registry.v1"

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
    ) -> EdgeRegistrySnapshot:
        decisions = tuple(
            EdgeDecision(
                definition.edge_id,
                definition.version,
                *definition.evaluate(
                    sample_size=sample_size,
                    out_of_sample=out_of_sample,
                    replicated=replicated,
                    observed_effect_size=observed_effect_size,
                    uncertainty_lower_bound=uncertainty_lower_bound,
                    out_of_sample_evidence_id=out_of_sample_evidence_id,
                    replication_evidence_id=replication_evidence_id,
                ),
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
