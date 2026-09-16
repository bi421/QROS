"""Governed bridge from Research Claims into the existing evidence graph.

The bridge deliberately does not mutate historical evidence envelopes. A claim
owns a content-addressed plan and references existing immutable evidence
artifacts by hash. This lets the SaaS layer add research intent without
rewriting the established evidence store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from researchos.claims.claim import ResearchClaim
from researchos.evidence.repository import EvidenceRepository
from researchos.storage.repository import ResearchRepository


@dataclass(frozen=True)
class ClaimEvidenceGraph:
    claim_id: str
    claim_hash: str
    plan_hash: str
    evidence_hashes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_type": "ClaimEvidenceGraph",
            "claim_id": self.claim_id,
            "claim_hash": self.claim_hash,
            "plan_hash": self.plan_hash,
            "evidence_hashes": list(self.evidence_hashes),
        }


class ResearchClaimEvidenceGraph:
    """Build and verify a claim → plan → evidence projection.

    Evidence artifacts remain append-only and are never rewritten merely to
    attach research intent. The projection is persisted as an ordinary
    ResearchOS object so it can later be migrated to a tenant-scoped SaaS
    store without changing the research contract.
    """

    def __init__(self, repository: ResearchRepository | None = None) -> None:
        self._repository = repository or ResearchRepository(db_path=":memory:")
        self._evidence = EvidenceRepository(self._repository)

    @property
    def evidence_repository(self) -> EvidenceRepository:
        return self._evidence

    def attach(self, claim: ResearchClaim, evidence_hashes: list[str] | tuple[str, ...]) -> ClaimEvidenceGraph:
        if not claim.is_plan_locked:
            raise ValueError("ResearchClaim plan must be locked before evidence can be attached")
        if not claim.plan_hash:
            raise ValueError("ResearchClaim has no plan_hash")

        normalized = tuple(sorted(set(evidence_hashes)))
        for evidence_hash in normalized:
            if self._evidence.get_artifact(evidence_hash) is None:
                raise ValueError(f"Evidence artifact {evidence_hash} does not exist")

        claim_copy = claim.clone()
        for evidence_hash in normalized:
            claim_copy.add_evidence(evidence_hash)
        self._repository.save_object(claim_copy)

        graph = ClaimEvidenceGraph(
            claim_id=claim_copy.id,
            claim_hash=claim_copy.claim_hash,
            plan_hash=claim_copy.plan_hash,
            evidence_hashes=normalized,
        )
        self._repository.save_object(_GraphObject(graph))
        return graph

    def get(self, claim_id: str) -> ClaimEvidenceGraph | None:
        data = self._repository.load_by_id(f"claim-evidence:{claim_id}")
        if data is None:
            return None
        return ClaimEvidenceGraph(
            claim_id=data["claim_id"],
            claim_hash=data["claim_hash"],
            plan_hash=data["plan_hash"],
            evidence_hashes=tuple(data.get("evidence_hashes", [])),
        )

    def verify(self, claim_id: str) -> bool:
        graph = self.get(claim_id)
        if graph is None:
            return False
        claim_data = self._repository.load_by_id(claim_id)
        if claim_data is None or claim_data.get("object_type") != "ResearchClaim":
            return False
        if claim_data.get("plan_hash") != graph.plan_hash:
            return False
        return all(self._evidence.get_artifact(h) is not None for h in graph.evidence_hashes)

    def close(self) -> None:
        self._repository.close()


class _GraphObject:
    def __init__(self, graph: ClaimEvidenceGraph) -> None:
        self.id = f"claim-evidence:{graph.claim_id}"
        self.created_at = ""
        self._graph = graph

    def to_dict(self) -> dict[str, Any]:
        return self._graph.to_dict() | {"id": self.id, "created_at": self.created_at}


__all__ = ["ClaimEvidenceGraph", "ResearchClaimEvidenceGraph"]
