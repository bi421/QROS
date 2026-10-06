from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "qros_agent.py"
CONTRACT = ROOT / "docs" / "engineering" / "tasks" / "qros-agent-v1.md"


def load_agent():
    spec = importlib.util.spec_from_file_location("qros_agent", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_valid_contract_and_repairable_failure_produce_proposal() -> None:
    agent = load_agent()
    decision = agent.run(
        CONTRACT,
        "ruff check failed: E501 line too long",
        attempt_limit=1,
    )

    assert decision.status == "PROPOSAL_READY"
    assert decision.classification["category"] == "formatting/static failure"
    assert isinstance(decision.classification["evidence"], list)
    assert decision.proposal["allowed"] is True
    assert decision.proposal["governed_action"] == ["ruff", "format"]
    assert decision.next_boundary == "governed-executor"


def test_ambiguous_failure_stops() -> None:
    agent = load_agent()
    decision = agent.run(
        CONTRACT,
        "Traceback (most recent call last)\nassertionerror: expected x but got y",
        attempt_limit=1,
    )

    assert decision.status == "STOP"
    assert decision.proposal["allowed"] is False
    assert decision.next_boundary == "human-review"


def test_zero_attempt_limit_stops() -> None:
    agent = load_agent()
    decision = agent.run(
        CONTRACT,
        "ruff check failed: E501 line too long",
        attempt_limit=0,
    )

    assert decision.status == "STOP"
    assert decision.proposal["allowed"] is False
    assert decision.proposal["attempt_limit"] == 0


def test_empty_log_stops() -> None:
    agent = load_agent()
    decision = agent.run(CONTRACT, "   ", attempt_limit=1)

    assert decision.status == "STOP"
    assert decision.classification["category"] == "ambiguous/unsafe"
    assert decision.proposal["allowed"] is False


def test_invalid_contract_stops_before_classification(tmp_path: Path) -> None:
    agent = load_agent()
    invalid = tmp_path / "invalid.md"
    invalid.write_text("# invalid\n", encoding="utf-8")

    decision = agent.run(invalid, "ruff check failed: E501", attempt_limit=1)

    assert decision.status == "STOP"
    assert decision.task_contract["valid"] is False
    assert decision.next_boundary == "human-review"


def test_cli_emits_machine_readable_decision(tmp_path: Path) -> None:
    log = tmp_path / "ci.log"
    log.write_text("ruff check failed: E501 line too long\\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(CONTRACT),
            str(log),
            "--attempt-limit",
            "1",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    decision = json.loads(result.stdout)
    assert decision["status"] == "PROPOSAL_READY"
    assert decision["next_boundary"] == "governed-executor"
    assert isinstance(decision["classification"]["evidence"], list)
    assert decision["proposal"]["allowed"] is True


def test_executor_requires_human_approval() -> None:
    agent = load_agent()
    result = agent.execute_proposal(
        CONTRACT,
        {"allowed": True, "governed_action": ["ruff", "format"]},
        ["ruff", "format", "scripts/qros_agent.py"],
        approved=False,
        attempt_limit=1,
    )

    assert result.status == "DRY_RUN"
    assert result.returncode is None
    assert result.diff == ""
    assert result.next_boundary == "human-approval"


def test_executor_rejects_scope_escape() -> None:
    agent = load_agent()
    result = agent.execute_proposal(
        CONTRACT,
        {"allowed": True},
        ["ruff", "format", "README.md"],
        approved=True,
        attempt_limit=1,
    )

    assert result.status == "STOP"
    assert result.returncode is None
    assert "escapes task scope" in result.stderr


def test_executor_rejects_unsupported_command() -> None:
    agent = load_agent()
    result = agent.execute_proposal(
        CONTRACT,
        {"allowed": True},
        ["git", "status"],
        approved=True,
        attempt_limit=1,
    )

    assert result.status == "STOP"
    assert "allowlist" in result.stderr


def test_executor_rejects_command_action_mismatch() -> None:
    agent = load_agent()
    result = agent.execute_proposal(
        CONTRACT,
        {"allowed": True, "governed_action": ["ruff", "check"]},
        ["ruff", "format", "scripts/qros_agent.py"],
        approved=True,
        attempt_limit=1,
    )

    assert result.status == "STOP"
    assert "does not match governed proposal action" in result.stderr


def test_executor_rejects_unapproved_proposal() -> None:
    agent = load_agent()
    result = agent.execute_proposal(
        CONTRACT,
        {"allowed": False, "governed_action": ["ruff", "format"]},
        ["ruff", "format", "scripts/qros_agent.py"],
        approved=True,
        attempt_limit=1,
    )

    assert result.status == "STOP"
    assert "not authorized" in result.stderr
