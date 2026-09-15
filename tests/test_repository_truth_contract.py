from __future__ import annotations

import re
from pathlib import Path


def test_macro_storage_public_api_does_not_export_skeletons() -> None:
    from researchos.macro import storage

    assert storage.__all__ == ["BaseStore"]
    assert not hasattr(storage, "JsonStore")
    assert not hasattr(storage, "ParquetStore")


def test_scope_guard_rejects_root_level_python_files() -> None:
    text = Path("scripts/check_scope.py").read_text(encoding="utf-8")
    assert re.search(r'^[^/]+\\.py\\$', text, re.MULTILINE)


def test_walkforward_artifact_is_not_claimed_verified_when_missing() -> None:
    record = Path("docs/research/xauusd_m1_b_level_validation_record.md").read_text(encoding="utf-8")
    assert "HISTORICAL ARTIFACT UNVERIFIED" in record
    assert "git log --all --full-history -- artifacts/xauusd_m1_walkforward.json" in record
