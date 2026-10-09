"""
Version control for ResearchOS objects and methodology.

Based on Article XVII: Object Model â€” all objects are version-controlled.
Based on Article III: Principles â€” all parameters are version-controlled.

Every ResearchOS object and methodology parameter has a version
that is tracked and immutable.
"""

from __future__ import annotations

from typing import Any
from dataclasses import dataclass, field

from researchos.core.timestamp import utc_now


@dataclass
class Version:
    """
    A version identifier for ResearchOS objects.

    Uses semantic versioning: MAJOR.MINOR.PATCH

    - MAJOR: Breaking changes to methodology or rules
    - MINOR: Backward-compatible additions
    - PATCH: Bug fixes and non-breaking changes
    """

    major: int = 1
    minor: int = 0
    patch: int = 0

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __lt__(self, other: Version) -> bool:
        return (self.major, self.minor, self.patch) < (
            other.major,
            other.minor,
            other.patch,
        )

    def bump_major(self) -> Version:
        return Version(self.major + 1, 0, 0)

    def bump_minor(self) -> Version:
        return Version(self.major, self.minor + 1, 0)

    def bump_patch(self) -> Version:
        return Version(self.major, self.minor, self.patch + 1)


@dataclass
class VersionHistory:
    """
    Complete version history for a ResearchOS object.

    All changes are tracked with timestamps and reasons.
    """

    versions: list[dict[str, Any]] = field(default_factory=list)

    def __init__(self, initial_version: Version | None = None):
        self.versions = []
        if initial_version:
            self.add_version(initial_version, "Initial version")

    def add_version(
        self,
        version: Version,
        reason: str,
        author: str | None = None,
    ) -> None:
        """
        Add a new version entry to the history.

        Args:
            version: The version being added.
            reason: Reason for the version change.
            author: Optional author of the change.
        """
        self.versions.append(
            {
                "version": str(version),
                "timestamp": utc_now().isoformat(),
                "reason": reason,
                "author": author,
            }
        )

    @property
    def current_version(self) -> Version | None:
        """Get the current version."""
        if not self.versions:
            return None
        v_str = self.versions[-1]["version"]
        parts = v_str.split(".")
        return Version(int(parts[0]), int(parts[1]), int(parts[2]))

    def to_dict(self) -> dict[str, any]:
        return {"versions": self.versions}
