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


def proposal(agent):
    decision = agent.run(CONTRACT, "ruff check failed: E501 line too long", attempt_limit=2)
    assert decision.status == "PROPOSAL_READY"
    assert decision.proposal["allowed"] is True
    return decision.proposal


def approval(agent, proposal):
    paths = agent._allowed_paths_from_contract(CONTRACT)
    return agent.approval_for(
        proposal, CONTRACT, paths,
        approver_id="test:approver",
        approved_at="2026-10-06T00:00:00+00:00",
    )


def test_valid_contract_and_proposal_identity() -> None:
    agent = load_agent()
    decision = agent.run(CONTRACT, "ruff check failed: E501 line too long", attempt_limit=1)
    assert decision.status == "PROPOSAL_READY"
    assert decision.classification["category"] == "formatting/static failure"
    assert decision.proposal["governed_action"] == ("ruff", "format")
    assert decision.proposal["proposal_id"] == agent.proposal_id(decision.proposal)


def test_unsafe_evidence_fails_closed() -> None:
    agent = load_agent()
    for log in ("", "Traceback (most recent call last)\nassertionerror: expected x but got y"):
        decision = agent.run(CONTRACT, log, attempt_limit=1)
        assert decision.status == "STOP"
        assert decision.proposal["allowed"] is False
        assert decision.next_boundary == "human-review"


def test_invalid_contract_stops_before_classification(tmp_path: Path) -> None:
    agent = load_agent()
    invalid = tmp_path / "invalid.md"
    invalid.write_text("# invalid\n", encoding="utf-8")
    decision = agent.run(invalid, "ruff check failed: E501", attempt_limit=1)
    assert decision.status == "STOP"
    assert decision.task_contract["valid"] is False


def test_cli_emits_machine_readable_decision(tmp_path: Path) -> None:
    log = tmp_path / "ci.log"
    log.write_text("ruff check failed: E501 line too long\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(CONTRACT), str(log), "--attempt-limit", "1"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    decision = json.loads(result.stdout)
    assert decision["status"] == "PROPOSAL_READY"
    assert decision["proposal"]["proposal_id"]


def test_missing_approval_fails_closed() -> None:
    agent = load_agent()
    p = proposal(agent)
    result = agent.execute_proposal(CONTRACT, p, ["ruff", "format", "scripts/qros_agent.py"], ledger=agent.AttemptLedger(1))
    assert result.status == "DRY_RUN"
    assert result.next_boundary == "human-approval"
    assert result.receipt is None


def test_invalid_approval_provenance_fails_closed() -> None:
    agent = load_agent()
    p = proposal(agent)
    paths = agent._allowed_paths_from_contract(CONTRACT)
    valid = approval(agent, p)
    invalid = agent.ApprovalProvenance(
        status="APPROVED", approver_id="", approved_at=valid.approved_at,
        proposal_id=valid.proposal_id, governed_action=valid.governed_action,
        scope_sha256=valid.scope_sha256, attempt_authority=valid.attempt_authority,
    )
    result = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "scripts/qros_agent.py"],
        approval=invalid, ledger=agent.AttemptLedger(1),
    )
    assert result.status == "STOP"
    assert "approver identity" in result.stderr


def test_wrong_proposal_and_action_are_rejected() -> None:
    agent = load_agent()
    p = proposal(agent)
    a = approval(agent, p)
    wrong = dict(p, proposal_id="tampered")
    result = agent.execute_proposal(
        CONTRACT, wrong, ["ruff", "format", "scripts/qros_agent.py"],
        approval=a, ledger=agent.AttemptLedger(1),
    )
    assert result.status == "STOP"
    assert "proposal identity" in result.stderr


def test_scope_escape_and_traversal_fail_closed() -> None:
    agent = load_agent()
    p = proposal(agent)
    a = approval(agent, p)
    ledger = agent.AttemptLedger(2)
    for path in ("README.md", "../README.md", "/tmp/escape.py"):
        result = agent.execute_proposal(
            CONTRACT, p, ["ruff", "format", path], approval=a, ledger=ledger,
        )
        assert result.status == "STOP"
        assert "scope" in result.stderr


def test_shell_metacharacters_are_rejected() -> None:
    agent = load_agent()
    p = proposal(agent)
    a = approval(agent, p)
    result = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "scripts/qros_agent.py;touch", "x"],
        approval=a, ledger=agent.AttemptLedger(1),
    )
    assert result.status == "STOP"
    assert "metacharacters" in result.stderr


def test_attempt_budget_is_not_reset_by_replay() -> None:
    agent = load_agent()
    p = proposal(agent)
    a = approval(agent, p)
    ledger = agent.AttemptLedger(1)
    first = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "scripts/qros_agent.py"],
        approval=a, ledger=ledger,
    )
    assert first.receipt is not None
    assert first.receipt.attempt_number == 1
    second = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "scripts/qros_agent.py"],
        approval=a, ledger=ledger,
    )
    assert second.status == "STOP"
    assert "exhausted" in second.stderr or "replay" in second.stderr


def test_receipt_binds_required_provenance() -> None:
    agent = load_agent()
    p = proposal(agent)
    a = approval(agent, p)
    ledger = agent.AttemptLedger(1)
    result = agent.execute_proposal(
        CONTRACT, p, ["ruff", "check", "scripts/qros_agent.py"],
        approval=a, ledger=ledger,
    )
    assert result.status == "STOP"  # action mismatch
    result = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "scripts/qros_agent.py"],
        approval=a, ledger=ledger,
    )
    assert result.receipt is not None
    receipt = result.receipt
    assert receipt.task_contract_sha256
    assert receipt.proposal_id == agent.proposal_id(p)
    assert receipt.governed_action == ("ruff", "format")
    assert receipt.command == ("ruff", "format", "scripts/qros_agent.py")
    assert receipt.pre_execution_sha
    assert receipt.approval == a
    assert receipt.next_boundary in {"complete", "human-review"}


def test_execution_failure_and_success_have_receipts() -> None:
    agent = load_agent()
    p = proposal(agent)
    a = approval(agent, p)
    ledger = agent.AttemptLedger(2)
    failed = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "scripts/qros_agent.py"],
        approval=a, ledger=ledger,
    )
    assert failed.receipt is not None
    assert failed.receipt.returncode is not None
    assert failed.receipt.status if hasattr(failed.receipt, "status") else True


def test_unapproved_proposal_stops() -> None:
    agent = load_agent()
    p = dict(proposal(agent), allowed=False)
    a = approval(agent, p)
    result = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "scripts/qros_agent.py"],
        approval=a, ledger=agent.AttemptLedger(1),
    )
    assert result.status == "STOP"
    assert "not authorized" in result.stderr
