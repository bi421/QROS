"""Regression tests for the governed static type-checking boundary."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_mypy_governed_scope_is_explicit_and_pinned() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"mypy==2.3.1"' in pyproject
    assert '[tool.mypy]' in pyproject
    assert 'python_version = "3.12"' in pyproject
    assert 'files = [' in pyproject
    for governed_file in (
        '"researchos/saas/api.py"',
        '"researchos/saas/contracts.py"',
        '"researchos/saas/claim_api.py"',
        '"researchos/saas/evidence_api.py"',
    ):
        assert governed_file in pyproject
    assert "disallow_untyped_defs = true" in pyproject


def test_ci_executes_the_governed_static_type_check() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "name: Static Type Check" in workflow
    assert "name: Setup Python 3.12" in workflow
    assert 'python-version: "3.12"' in workflow
    assert "name: Run mypy" in workflow
    assert "run: mypy" in workflow
