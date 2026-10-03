from __future__ import annotations

import json
from datetime import datetime
from typing import Any, TypeVar, cast

from researchos.core.identity import deterministic_hash, generate_id
from researchos.core.lifecycle import Lifecycle
from researchos.core.timestamp import parse_timestamp, utc_now


T = TypeVar("T", bound="BaseObject")


class BaseObject:
    """
    Foundational ResearchOS object.

    Guarantees:
      - deterministic content hashing
      - deterministic serialization
      - lifecycle reconstruction
      - stable object identity
    """

    def __init__(
        self,
        id: str | None = None,
        created_at: datetime | None = None,
        ontology_tags: list[str] | None = None,
    ):
        self.created_at = created_at or utc_now()
        self.ontology_tags = list(ontology_tags or [])
        self.lifecycle = Lifecycle()
        self._hash: str | None = None

        if id is None:
            seed = "|".join(sorted(self.ontology_tags)) or self.__class__.__name__
            self.id = generate_id(seed)
        else:
            self.id = id

    def _to_hashable_dict(self) -> dict[str, Any]:
        return {
            "ontology_tags": sorted(self.ontology_tags),
        }

    def compute_hash(self) -> str:
        return deterministic_hash(self._to_hashable_dict())

    @property
    def hash(self) -> str:
        if self._hash is None:
            self._hash = self.compute_hash()
        return self._hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_type": self.__class__.__name__,
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "ontology_tags": list(self.ontology_tags),
            "lifecycle": self.lifecycle.to_dict(),
            "hash": self.compute_hash(),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            indent=2,
            sort_keys=True,
            default=str,
        )

    @classmethod
    def from_dict(cls: type[T], data: dict[str, Any]) -> T:
        obj = cast(T, cls.__new__(cls))

        obj.id = data.get("id")

        created_at = data.get("created_at")
        obj.created_at = parse_timestamp(created_at) if created_at else utc_now()

        obj.ontology_tags = list(data.get("ontology_tags", []))

        lifecycle_data = data.get(
            "lifecycle",
            {"transitions": []},
        )

        obj.lifecycle = Lifecycle.from_dict(lifecycle_data)
        obj._hash = None

        return obj

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaseObject):
            return False
        return self.hash == other.hash

    def __hash__(self) -> int:
        return hash(self.id)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id[:8]}...)"
