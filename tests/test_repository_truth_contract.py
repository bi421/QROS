from __future__ import annotations

import ast
import re
from pathlib import Path

from scripts.check_scope import is_new_native_quant_python_module


def test_macro_storage_public_api_does_not_export_skeletons() -> None:
    from researchos.macro import storage

    assert storage.__all__ == ["BaseStore"]
    assert not hasattr(storage, "JsonStore")
    assert not hasattr(storage, "ParquetStore")


def test_scope_guard_rejects_root_level_python_files() -> None:
    text = Path("scripts/check_scope.py").read_text(encoding="utf-8")
    assert re.search(r"^\[^/\]+\.py$", text, re.MULTILINE)


def test_scope_guard_rejects_new_native_quant_python_modules() -> None:
    assert is_new_native_quant_python_module(
        "researchos/engines/quant/new_api.py"
    )
    assert not is_new_native_quant_python_module(
        "researchos/engines/quant/python/cpp_quant.py"
    )
    assert not is_new_native_quant_python_module(
        "researchos/engines/quant/tests/test_bridge.py"
    )
    assert not is_new_native_quant_python_module(
        "researchos/quant_engine/new_api.py"
    )


def test_walkforward_artifact_is_not_claimed_verified_when_missing() -> None:
    record = Path("docs/research/xauusd_m1_b_level_validation_record.md").read_text(
        encoding="utf-8"
    )
    assert "HISTORICAL ARTIFACT UNVERIFIED" in record
    assert "git log --all --full-history -- artifacts/xauusd_m1_walkforward.json" in record


def test_repository_truth_audit_treats_protocols_as_interfaces() -> None:
    source = Path("researchos/research_core/contracts.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    runner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ResearchRunner"
    )
    assert any(
        isinstance(base, ast.Name) and base.id == "Protocol"
        for base in runner.bases
    )


def test_repository_truth_audit_has_protocol_exemption_and_document_context() -> None:
    source = Path("scripts/audit_repository_truth.py").read_text(encoding="utf-8")
    assert "is_protocol_class" in source
    assert "evidence integrity notice" in source
