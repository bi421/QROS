"""Regression tests for the governed static type-checking boundary."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_mypy_governed_scope_is_explicit_and_pinned() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"mypy==2.3.1"' in pyproject
    assert '[tool.mypy]' in pyproject
    assert 'files = [' in pyproject
    assert '"researchos/saas/api.py"' in pyproject
    assert '"researchos/saas/contracts.py"' in pyproject
    assert "disallow_untyped_defs = true" in pyproject
    assert '[tool.mypy-baseline]' in pyproject
    assert 'baseline_path = "mypy-baseline.txt"' in pyproject


def test_ci_does_not_duplicate_mypy_and_ratchet_workflow_is_canonical() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "name: Static Type Check" not in ci
    assert "name: Mypy Ratchet" in ci
    assert "--follow-imports=skip" in ci
    assert "mypy-baseline filter" in ci
    assert not (ROOT / ".github" / "workflows" / "mypy.yml").exists()
