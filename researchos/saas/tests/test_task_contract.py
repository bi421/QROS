from __future__ import annotations

from pathlib import Path

from scripts.validate_task_contract import validate_contract


VALID = """# QROS Engineering Task Contract v1

## Task
- ID: TASK-001
- Goal: Validate task contracts
- Why: Prevent incomplete autonomous work

## Scope
### Allowed
- scripts/validate_task_contract.py
### Forbidden
- production migrations

## Preconditions
- Current branch/ref: main
- Required existing contracts: AGENT_CONTRACT.md
- Required dependencies: Python

## Acceptance criteria
- [ ] Validator rejects incomplete contracts

## Validation
- [ ] pre-commit
- [ ] python scripts/preflight.py --profile fast
- [ ] targeted tests: contract validator

## Risk
- Security impact: none
- Tenant-isolation impact: none
- Data-integrity impact: none
- Migration impact: none
- API compatibility impact: none

## Autonomy limits
- Maximum repair attempts: 2
- Stop conditions: ambiguous failure
- Human approval required for: production changes

## Completion evidence
- Commit: pending
- PR: pending
- CI run(s): pending
- Observed final status: pending
- Known limitations: none
"""


def test_valid_contract_passes(tmp_path: Path) -> None:
    path = tmp_path / "task.md"
    path.write_text(VALID, encoding="utf-8")
    assert validate_contract(path) == []


def test_missing_required_section_fails(tmp_path: Path) -> None:
    path = tmp_path / "task.md"
    path.write_text(VALID.replace("## Risk", "## Risk removed"), encoding="utf-8")
    assert "missing required section: ## Risk" in validate_contract(path)


def test_unfilled_required_field_fails(tmp_path: Path) -> None:
    path = tmp_path / "task.md"
    path.write_text(VALID.replace("- Goal: Validate task contracts", "- Goal:"), encoding="utf-8")
    assert any("unfilled required field: - Goal:" == error for error in validate_contract(path))


def test_empty_allowed_scope_fails(tmp_path: Path) -> None:
    path = tmp_path / "task.md"
    path.write_text(VALID.replace("- scripts/validate_task_contract.py", ""), encoding="utf-8")
    assert "scope allowed list must contain at least one non-empty item" in validate_contract(path)


def test_missing_acceptance_checklist_fails(tmp_path: Path) -> None:
    path = tmp_path / "task.md"
    path.write_text(VALID.replace("- [ ] Validator rejects incomplete contracts", ""), encoding="utf-8")
    assert "acceptance criteria must contain at least one non-empty checklist item" in validate_contract(path)
