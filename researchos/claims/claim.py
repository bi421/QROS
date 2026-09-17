"""Research Claim — the durable unit of empirical research intent."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from researchos.core.base_object import BaseObject
from researchos.core.identity import generate_id
from researchos.core.timestamp import parse_timestamp, utc_now


class ResearchClaimType(str, Enum):
    EMPIRICAL = "empirical"
    CAUSAL = "causal"
    PREDICTIVE = "predictive"
    DESCRIPTIVE = "descriptive"
    ROBUSTNESS = "robustness"


class EvidenceState(str, Enum):
    UNTESTED = "UNTESTED"
    TESTED = "TESTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    CONTRADICTED = "CONTRADICTED"
    CANDIDATE = "CANDIDATE"
    ROBUSTNESS = "ROBUSTNESS"
    REPLICATION = "REPLICATION"
    SUPPORTED = "SUPPORTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ResearchPlan:
    """Machine-readable analysis plan that becomes immutable when locked."""

    hypothesis: str
    sample_definition: str
    features: tuple[str, ...]
    labels: tuple[str, ...]
    train_validation_test: str
    exclusions: tuple[str, ...]
    costs_slippage: str
    statistical_tests: tuple[str, ...]
    metrics: tuple[str, ...]
    stopping_rules: tuple[str, ...]
    multiple_testing_policy: str
    replication_policy: str

    def __post_init__(self) -> None:
        required = {
            "hypothesis": self.hypothesis,
            "sample_definition": self.sample_definition,
            "train_validation_test": self.train_validation_test,
            "costs_slippage": self.costs_slippage,
            "multiple_testing_policy": self.multiple_testing_policy,
            "replication_policy": self.replication_policy,
        }
        for name, value in required.items():
            if not value.strip():
                raise ValueError(f"ResearchPlan.{name} is required")
        if not self.features:
            raise ValueError("ResearchPlan.features must not be empty")
        if not self.metrics:
            raise ValueError("ResearchPlan.metrics must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis": self.hypothesis,
            "sample_definition": self.sample_definition,
            "features": list(self.features),
            "labels": list(self.labels),
            "train_validation_test": self.train_validation_test,
            "exclusions": list(self.exclusions),
            "costs_slippage": self.costs_slippage,
            "statistical_tests": list(self.statistical_tests),
            "metrics": list(self.metrics),
            "stopping_rules": list(self.stopping_rules),
            "multiple_testing_policy": self.multiple_testing_policy,
            "replication_policy": self.replication_policy,
        }

    @property
    def content_hash(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResearchPlan":
        return cls(
            hypothesis=str(data["hypothesis"]),
            sample_definition=str(data["sample_definition"]),
            features=tuple(str(v) for v in data.get("features", [])),
            labels=tuple(str(v) for v in data.get("labels", [])),
            train_validation_test=str(data["train_validation_test"]),
            exclusions=tuple(str(v) for v in data.get("exclusions", [])),
            costs_slippage=str(data["costs_slippage"]),
            statistical_tests=tuple(str(v) for v in data.get("statistical_tests", [])),
            metrics=tuple(str(v) for v in data.get("metrics", [])),
            stopping_rules=tuple(str(v) for v in data.get("stopping_rules", [])),
            multiple_testing_policy=str(data["multiple_testing_policy"]),
            replication_policy=str(data["replication_policy"]),
        )


class ResearchClaim(BaseObject):
    """Versioned, auditable statement that can accumulate empirical evidence."""

    _SEMANTIC_FIELDS = frozenset(
        {
            "statement",
            "claim_type",
            "target_population",
            "instrument",
            "horizon",
            "timestamp_policy",
            "economic_rationale",
            "falsification_conditions",
            "primary_metrics",
            "minimum_evidence_requirements",
            "creator",
            "workspace_id",
            "research_id",
            "version",
            "parent_claim_id",
            "research_plan",
            "plan_hash",
        }
    )

    def __init__(
        self,
        statement: str,
        claim_type: ResearchClaimType | str = ResearchClaimType.EMPIRICAL,
        target_population: str = "",
        instrument: str = "",
        horizon: str = "",
        timestamp_policy: str = "",
        economic_rationale: str = "",
        falsification_conditions: tuple[str, ...] | list[str] | None = None,
        primary_metrics: tuple[str, ...] | list[str] | None = None,
        minimum_evidence_requirements: tuple[str, ...] | list[str] | None = None,
        creator: str = "",
        workspace_id: str = "",
        research_id: str | None = None,
        ontology_tags: list[str] | None = None,
        id: str | None = None,
        version: int = 1,
        parent_claim_id: str | None = None,
    ):
        if not statement.strip():
            raise ValueError("ResearchClaim.statement is required")
        if version < 1:
            raise ValueError("ResearchClaim.version must be >= 1")
        if version == 1 and parent_claim_id is not None:
            raise ValueError("version 1 cannot have parent_claim_id")
        if version > 1 and not parent_claim_id:
            raise ValueError("version > 1 requires parent_claim_id")

        normalized_type = ResearchClaimType(claim_type)
        if id is None:
            seed = f"ResearchClaim|{workspace_id}|{statement}|{normalized_type.value}|{version}|{parent_claim_id or ''}"
            id = generate_id(seed)

        super().__init__(id=id, ontology_tags=ontology_tags)
        self.statement = statement.strip()
        self.claim_type = normalized_type
        self.target_population = target_population.strip()
        self.instrument = instrument.strip()
        self.horizon = horizon.strip()
        self.timestamp_policy = timestamp_policy.strip()
        self.economic_rationale = economic_rationale.strip()
        self.falsification_conditions = tuple(falsification_conditions or ())
        self.primary_metrics = tuple(primary_metrics or ())
        self.minimum_evidence_requirements = tuple(minimum_evidence_requirements or ())
        self.creator = creator.strip()
        self.workspace_id = workspace_id.strip()
        self.research_id = research_id
        self.version = version
        self.parent_claim_id = parent_claim_id
        self.evidence_state = EvidenceState.UNTESTED
        self.research_plan: ResearchPlan | None = None
        self.plan_locked_at: datetime | None = None
        self.plan_hash: str | None = None
        self.experiment_ids: tuple[str, ...] = ()
        self.evidence_hashes: tuple[str, ...] = ()
        self._plan_lock_active = False

    def __setattr__(self, name: str, value: Any) -> None:
        if name in self._SEMANTIC_FIELDS and getattr(self, "_plan_lock_active", False):
            raise AttributeError(
                f"ResearchClaim.{name} is immutable after plan lock; fork a new claim version"
            )
        super().__setattr__(name, value)

    @property
    def is_plan_locked(self) -> bool:
        return self.plan_locked_at is not None

    @property
    def claim_hash(self) -> str:
        return self.compute_hash()

    def lock_plan(self, plan: ResearchPlan) -> str:
        """Lock the confirmatory research plan exactly once."""
        if self.is_plan_locked:
            if self.plan_hash == plan.content_hash:
                return self.plan_hash
            raise ValueError("Research plan is already locked and cannot be replaced")
        self.research_plan = plan
        self.plan_hash = plan.content_hash
        self.plan_locked_at = utc_now()
        self._hash = None
        self._plan_lock_active = True
        return self.plan_hash

    def add_experiment(self, experiment_id: str) -> None:
        if not experiment_id.strip():
            raise ValueError("experiment_id is required")
        if experiment_id not in self.experiment_ids:
            self.experiment_ids = (*self.experiment_ids, experiment_id)
            self._hash = None

    def add_evidence(self, evidence_hash: str) -> None:
        if not evidence_hash.strip():
            raise ValueError("evidence_hash is required")
        if evidence_hash not in self.evidence_hashes:
            self.evidence_hashes = (*self.evidence_hashes, evidence_hash)
            self._hash = None

    def set_evidence_state(self, state: EvidenceState | str) -> None:
        self.evidence_state = EvidenceState(state)
        self._hash = None

    def fork_version(self, statement: str | None = None) -> "ResearchClaim":
        return ResearchClaim(
            statement=statement or self.statement,
            claim_type=self.claim_type,
            target_population=self.target_population,
            instrument=self.instrument,
            horizon=self.horizon,
            timestamp_policy=self.timestamp_policy,
            economic_rationale=self.economic_rationale,
            falsification_conditions=self.falsification_conditions,
            primary_metrics=self.primary_metrics,
            minimum_evidence_requirements=self.minimum_evidence_requirements,
            creator=self.creator,
            workspace_id=self.workspace_id,
            research_id=self.research_id,
            ontology_tags=list(self.ontology_tags),
            version=self.version + 1,
            parent_claim_id=self.id,
        )

    def _to_hashable_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "claim_type": self.claim_type.value,
            "target_population": self.target_population,
            "instrument": self.instrument,
            "horizon": self.horizon,
            "timestamp_policy": self.timestamp_policy,
            "economic_rationale": self.economic_rationale,
            "falsification_conditions": sorted(self.falsification_conditions),
            "primary_metrics": sorted(self.primary_metrics),
            "minimum_evidence_requirements": sorted(self.minimum_evidence_requirements),
            "creator": self.creator,
            "workspace_id": self.workspace_id,
            "research_id": self.research_id or "",
            "version": self.version,
            "parent_claim_id": self.parent_claim_id or "",
            "plan_hash": self.plan_hash or "",
            "experiment_ids": sorted(self.experiment_ids),
            "evidence_hashes": sorted(self.evidence_hashes),
            "evidence_state": self.evidence_state.value,
            "ontology_tags": sorted(self.ontology_tags),
        }

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update(
            {
                "statement": self.statement,
                "claim_type": self.claim_type.value,
                "target_population": self.target_population,
                "instrument": self.instrument,
                "horizon": self.horizon,
                "timestamp_policy": self.timestamp_policy,
                "economic_rationale": self.economic_rationale,
                "falsification_conditions": list(self.falsification_conditions),
                "primary_metrics": list(self.primary_metrics),
                "minimum_evidence_requirements": list(self.minimum_evidence_requirements),
                "creator": self.creator,
                "workspace_id": self.workspace_id,
                "research_id": self.research_id,
                "version": self.version,
                "parent_claim_id": self.parent_claim_id,
                "evidence_state": self.evidence_state.value,
                "research_plan": self.research_plan.to_dict() if self.research_plan else None,
                "plan_locked_at": self.plan_locked_at.isoformat() if self.plan_locked_at else None,
                "plan_hash": self.plan_hash,
                "experiment_ids": list(self.experiment_ids),
                "evidence_hashes": list(self.evidence_hashes),
            }
        )
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchClaim":
        obj = super().from_dict(data)
        obj.statement = str(data["statement"])
        obj.claim_type = ResearchClaimType(data.get("claim_type", ResearchClaimType.EMPIRICAL.value))
        obj.target_population = str(data.get("target_population", ""))
        obj.instrument = str(data.get("instrument", ""))
        obj.horizon = str(data.get("horizon", ""))
        obj.timestamp_policy = str(data.get("timestamp_policy", ""))
        obj.economic_rationale = str(data.get("economic_rationale", ""))
        obj.falsification_conditions = tuple(data.get("falsification_conditions", []))
        obj.primary_metrics = tuple(data.get("primary_metrics", []))
        obj.minimum_evidence_requirements = tuple(data.get("minimum_evidence_requirements", []))
        obj.creator = str(data.get("creator", ""))
        obj.workspace_id = str(data.get("workspace_id", ""))
        obj.research_id = data.get("research_id")
        obj.version = int(data.get("version", 1))
        obj.parent_claim_id = data.get("parent_claim_id")
        obj.evidence_state = EvidenceState(data.get("evidence_state", EvidenceState.UNTESTED.value))
        plan_data = data.get("research_plan")
        obj.research_plan = ResearchPlan.from_dict(plan_data) if plan_data else None
        obj.plan_locked_at = None
        obj.plan_hash = data.get("plan_hash")
        obj.experiment_ids = tuple(data.get("experiment_ids", []))
        obj.evidence_hashes = tuple(data.get("evidence_hashes", []))
        locked_at = data.get("plan_locked_at")
        obj.plan_locked_at = parse_timestamp(locked_at) if locked_at else None
        obj._plan_lock_active = obj.plan_locked_at is not None
        return obj

    def clone(self) -> "ResearchClaim":
        return copy.deepcopy(self)
