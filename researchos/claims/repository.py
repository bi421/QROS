"""Persistence adapter for Research Claims."""

from __future__ import annotations

from researchos.claims.claim import ResearchClaim
from researchos.storage.repository import ResearchRepository


class ResearchClaimRepository:
    """Persist and retrieve claims through the canonical generic object store."""

    def __init__(self, repository: ResearchRepository | None = None) -> None:
        self._repository = repository or ResearchRepository(db_path=":memory:")

    def save(self, claim: ResearchClaim) -> ResearchClaim:
        self._repository.save_object(claim)
        return claim

    def get(self, claim_id: str) -> ResearchClaim | None:
        data = self._repository.load_by_id(claim_id)
        if data is None:
            return None
        if data.get("object_type") != "ResearchClaim":
            raise ValueError(f"Object {claim_id} is not a ResearchClaim")
        return ResearchClaim.from_dict(data)

    def list(self) -> list[ResearchClaim]:
        return [
            ResearchClaim.from_dict(data)
            for data in self._repository.load_by_type("ResearchClaim")
        ]

    def count(self) -> int:
        return self._repository.object_count("ResearchClaim")

    def close(self) -> None:
        self._repository.close()
