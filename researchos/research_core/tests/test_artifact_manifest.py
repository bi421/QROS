import pytest

from researchos.research_core.artifact_manifest import ArtifactManifest
from researchos.research_core.contracts import ResearchArtifact


def _artifact(i: str) -> ResearchArtifact:
    return ResearchArtifact(i, "result", "a" * 64)


def test_manifest_is_deterministic_independent_of_input_order():
    a, b = _artifact("a"), _artifact("b")
    first = ArtifactManifest.build("0" * 64, "1" * 64, [b, a])
    second = ArtifactManifest.build("0" * 64, "1" * 64, [a, b])
    assert first.artifacts == second.artifacts
    assert first.manifest_sha256 == second.manifest_sha256


def test_manifest_verifies_and_rejects_duplicate_ids():
    manifest = ArtifactManifest.build("0" * 64, "1" * 64, [_artifact("a")])
    assert manifest.verify(manifest.manifest_sha256)
    with pytest.raises(ValueError):
        ArtifactManifest.build("0" * 64, "1" * 64, [_artifact("a"), _artifact("a")])
