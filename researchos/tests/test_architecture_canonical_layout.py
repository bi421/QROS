from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_no_python_consumer_imports_legacy_data_engine() -> None:
    for path in ROOT.rglob("*.py"):
        if ".git" in path.parts:
            continue
        if path == Path(__file__).resolve():
            continue
        assert not any(
            module == "researchos.engines.data"
            or module.startswith("researchos.engines.data.")
            for module in _imported_modules(path)
        ), path


def test_no_root_level_python_scripts() -> None:
    allowed = {"__init__.py"}
    root_scripts = [
        path.name
        for path in ROOT.glob("*.py")
        if path.name not in allowed
    ]
    assert root_scripts == [], root_scripts
