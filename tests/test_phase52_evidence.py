from __future__ import annotations

import pytest

from scripts.run_phase52_evidence import _validate_repository_commit


def test_repository_commit_requires_exact_40_character_git_sha() -> None:
    assert _validate_repository_commit(
        "03191c86cdff541a03545ff521c667e4ccd733c9a"
    ) == "03191c86cdff541a03545ff521c667e4ccd733c9a"


@pytest.mark.parametrize(
    "value",
    [
        "unknown",
        "abc123",
        "0" * 39,
        "0" * 41,
        "g" * 40,
    ],
)
def test_repository_commit_rejects_non_exact_sha(value: str) -> None:
    with pytest.raises(ValueError, match="exact 40-character Git SHA"):
        _validate_repository_commit(value)
