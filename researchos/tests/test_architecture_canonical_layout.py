from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_no_python_consumer_imports_legacy_data_engine() -> None:
    for path in ROOT.rglob("*.py"):
        if ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "researchos.engines.data" not in text, path


def test_no_root_level_python_scripts() -> None:
    allowed = {"__init__.py"}
    root_scripts = [
        path.name
        for path in ROOT.glob("*.py")
        if path.name not in allowed
    ]
    assert root_scripts == [], root_scripts
