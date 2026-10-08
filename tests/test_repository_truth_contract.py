from __future__ import annotations

import ast
from pathlib import Path

from scripts.check_scope import (
    FORBIDDEN_NEW_PATHS,
    changed_paths,
    is_new_native_quant_python_module,
)


def test_macro_storage_public_api_does_not_export_skeletons() -> None:
    from researchos.macro import storage

    assert storage.__all__ == ["BaseStore"]
    assert not hasattr(storage, "JsonStore")
    assert not hasattr(storage, "ParquetStore")


def test_scope_guard_rejects_root_level_python_files() -> None:
    # Root-level Python scripts are forbidden; owned directories are allowed.
    assert any(pattern.search("analyze.py") for pattern in FORBIDDEN_NEW_PATHS)
    assert not any(
        pattern.search("scripts/analyze.py") for pattern in FORBIDDEN_NEW_PATHS
    )


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


def test_scope_guard_changed_paths_supports_added_only_filter() -> None:
    # Regression: main() calls changed_paths(base, staged, "A") to scope the
    # native-quant rule to newly added files. The guard used to crash with
    # TypeError because changed_paths had no diff_filter parameter.
    all_changed = changed_paths(None, False)
    added_only = changed_paths(None, False, "A")

    assert isinstance(all_changed, list)
    assert isinstance(added_only, list)
    # Added files are always a subset of Added/Copied/Modified/Renamed files.
    assert set(added_only).issubset(set(all_changed))


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


def test_scope_guard_covers_known_legacy_forensic_artifacts() -> None:
    source = Path("scripts/check_scope.py").read_text(encoding="utf-8")
    assert "qros_pybind11_forensic_audit" in source
    assert "cpp_true_production_v[1-9]" in source


def test_ci_installs_test_extra_and_dev_contains_live_signal_dependency() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'python -m pip install -e ".[dev,test,saas]"' in workflow
    assert '"yfinance>=0.2"' in pyproject
