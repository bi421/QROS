"""Immutable experience records for the adaptive learning loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class Experience:
    """One prediction/action/outcome observation.

    outcome is 1.0 for success and 0.0 for failure.  Partial outcomes are
    allowed for research evaluation, but callers must keep the value bounded.
    """

    experience_id: str
    state_key: str
    predicted_probability: float
    outcome: float
    action: str
    reward: float
    metadata: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.experience_id:
            raise ValueError("experience_id must not be empty")
        if not self.state_key:
            raise ValueError("state_key must not be empty")
        if not 0.0 <= self.predicted_probability <= 1.0:
            raise ValueError("predicted_probability must be in [0, 1]")
        if not 0.0 <= self.outcome <= 1.0:
            raise ValueError("outcome must be in [0, 1]")


class ExperienceStore:
    """Append-only in-memory experience store for v1.

    Persistence belongs behind this boundary; the learning engine never edits
    or deletes prior experiences.
    """

    def __init__(self, experiences: Iterable[Experience] = ()) -> None:
        self._experiences: list[Experience] = list(experiences)
        self._ids = {item.experience_id for item in self._experiences}
        if len(self._ids) != len(self._experiences):
            raise ValueError("duplicate experience_id")

    def append(self, experience: Experience) -> None:
        if experience.experience_id in self._ids:
            raise ValueError("experience_id already exists")
        self._experiences.append(experience)
        self._ids.add(experience.experience_id)

    def all(self) -> tuple[Experience, ...]:
        return tuple(self._experiences)

    def for_state(self, state_key: str) -> tuple[Experience, ...]:
        return tuple(item for item in self._experiences if item.state_key == state_key)
