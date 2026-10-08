from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

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


def approval(agent, proposal, ledger):
    paths = agent._allowed_paths_from_contract(CONTRACT)
    return agent.approval_for(
        proposal, CONTRACT, paths, ledger=ledger,
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
        cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    decision = json.loads(result.stdout)
    assert decision["status"] == "PROPOSAL_READY"
    assert decision["proposal"]["proposal_id"]


def test_ruff_check_flag_is_not_treated_as_scope_path() -> None:
    agent = load_agent()
    paths = agent._command_paths(
        ["ruff", "format", "--check", "scripts/qros_agent.py"]
    )
    assert paths == ((ROOT / "scripts" / "qros_agent.py").resolve(),)


def test_missing_approval_fails_closed() -> None:
    agent = load_agent()
    p = proposal(agent)
    ledger = agent.AttemptLedger(1)
    result = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "--check", "scripts/qros_agent.py"], ledger=ledger
    )
    assert result.status == "STOP"
    assert "explicit approval provenance is required" in result.stderr
    assert result.next_boundary == "human-review"
    assert result.receipt is None
    assert ledger.consumed_attempts == 0


def test_invalid_approval_provenance_fails_closed() -> None:
    agent = load_agent()
    p = proposal(agent)
    ledger = agent.AttemptLedger(1)
    valid = approval(agent, p, ledger)
    invalid = agent.ApprovalProvenance(
        status="APPROVED", approver_id="", approved_at=valid.approved_at,
        proposal_id=valid.proposal_id, governed_action=valid.governed_action,
        scope_sha256=valid.scope_sha256, attempt_authority=valid.attempt_authority,
    )
    result = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "--check", "scripts/qros_agent.py"],
        approval=invalid, ledger=ledger,
    )
    assert result.status == "STOP"
    assert "approver identity" in result.stderr
    assert ledger.consumed_attempts == 0



def test_approval_attempt_authority_is_bound_to_ledger() -> None:
    agent = load_agent()
    p = proposal(agent)
    ledger = agent.AttemptLedger(1)
    valid = approval(agent, p, ledger)
    invalid = agent.ApprovalProvenance(
        status=valid.status,
        approver_id=valid.approver_id,
        approved_at=valid.approved_at,
        proposal_id=valid.proposal_id,
        governed_action=valid.governed_action,
        scope_sha256=valid.scope_sha256,
        attempt_authority=agent._canonical_sha({
            "budget_id": "wrong-budget",
            "max_attempts": ledger.max_attempts,
            "task_contract_sha256": agent._task_contract_sha256(CONTRACT),
        }),
    )
    result = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "--check", "scripts/qros_agent.py"],
        approval=invalid, ledger=ledger,
    )
    assert result.status == "STOP"
    assert "attempt authority" in result.stderr
    assert ledger.consumed_attempts == 0


def test_approval_is_bound_to_governed_action_not_only_command() -> None:
    agent = load_agent()
    p = proposal(agent)
    ledger = agent.AttemptLedger(1)
    valid = approval(agent, p, ledger)
    forged = agent.ApprovalProvenance(
        status=valid.status,
        approver_id=valid.approver_id,
        approved_at=valid.approved_at,
        proposal_id=valid.proposal_id,
        governed_action=("ruff", "check"),
        scope_sha256=valid.scope_sha256,
        attempt_authority=valid.attempt_authority,
    )
    result = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "--check", "scripts/qros_agent.py"],
        approval=forged, ledger=ledger,
    )
    assert result.status == "STOP"
    assert "governed action" in result.stderr
    assert result.receipt is None
    assert ledger.consumed_attempts == 0


def test_approval_is_bound_to_task_scope_hash() -> None:
    agent = load_agent()
    p = proposal(agent)
    ledger = agent.AttemptLedger(1)
    valid = approval(agent, p, ledger)
    forged = agent.ApprovalProvenance(
        status=valid.status,
        approver_id=valid.approver_id,
        approved_at=valid.approved_at,
        proposal_id=valid.proposal_id,
        governed_action=valid.governed_action,
        scope_sha256=agent._canonical_sha(["scripts/some_other_scope.py"]),
        attempt_authority=valid.attempt_authority,
    )
    result = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "--check", "scripts/qros_agent.py"],
        approval=forged, ledger=ledger,
    )
    assert result.status == "STOP"
    assert "task scope" in result.stderr
    assert result.receipt is None
    assert ledger.consumed_attempts == 0


def test_wrong_proposal_is_rejected() -> None:
    agent = load_agent()
    p = proposal(agent)
    ledger = agent.AttemptLedger(1)
    a = approval(agent, p, ledger)
    wrong = dict(p, rationale=("tampered",))
    result = agent.execute_proposal(
        CONTRACT, wrong, ["ruff", "format", "--check", "scripts/qros_agent.py"],
        approval=a, ledger=ledger,
    )
    assert result.status == "STOP"
    assert "proposal identity" in result.stderr
    assert ledger.consumed_attempts == 0


def test_wrong_action_is_rejected() -> None:
    agent = load_agent()
    p = proposal(agent)
    ledger = agent.AttemptLedger(1)
    a = approval(agent, p, ledger)
    result = agent.execute_proposal(
        CONTRACT, p, ["ruff", "check", "scripts/qros_agent.py"],
        approval=a, ledger=ledger,
    )
    assert result.status == "STOP"
    assert "does not match governed proposal action" in result.stderr
    assert ledger.consumed_attempts == 0


def test_scope_escape_and_traversal_fail_closed() -> None:
    agent = load_agent()
    p = proposal(agent)
    ledger = agent.AttemptLedger(2)
    a = approval(agent, p, ledger)
    for path in ("README.md", "../README.md", "/tmp/escape.py"):
        result = agent.execute_proposal(
            CONTRACT, p, ["ruff", "format", path], approval=a, ledger=ledger,
        )
        assert result.status == "STOP"
        assert "scope" in result.stderr
    assert ledger.consumed_attempts == 0


def test_shell_metacharacters_are_rejected() -> None:
    agent = load_agent()
    p = proposal(agent)
    ledger = agent.AttemptLedger(1)
    a = approval(agent, p, ledger)
    result = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "scripts/qros_agent.py;touch"],
        approval=a, ledger=ledger,
    )
    assert result.status == "STOP"
    assert "metacharacters" in result.stderr
    assert ledger.consumed_attempts == 0


def test_attempt_budget_is_not_reset_by_replay() -> None:
    agent = load_agent()
    p = proposal(agent)
    ledger = agent.AttemptLedger(1)
    a = approval(agent, p, ledger)
    first = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "--check", "scripts/qros_agent.py"],
        approval=a, ledger=ledger,
    )
    assert first.receipt is not None
    assert first.receipt.attempt_number == 1
    assert ledger.consumed_attempts == 1
    second = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "--check", "scripts/qros_agent.py"],
        approval=a, ledger=ledger,
    )
    assert second.status == "STOP"
    assert "exhausted" in second.stderr or "replay" in second.stderr


def test_attempt_ledger_rejects_replay_and_budget_overrun() -> None:
    agent = load_agent()
    ledger = agent.AttemptLedger(2)
    first_receipt = agent._canonical_sha({"governed": "execution-a"})

    assert ledger.consume(first_receipt) == 1

    with pytest.raises(RuntimeError, match="replay"):
        ledger.consume(first_receipt)

    assert ledger.consume(agent._canonical_sha({"governed": "execution-b"})) == 2

    with pytest.raises(RuntimeError, match="exhausted"):
        ledger.consume(agent._canonical_sha({"governed": "execution-c"}))

    assert ledger.consumed_attempts == 2


def test_receipt_binds_required_provenance() -> None:
    agent = load_agent()
    p = proposal(agent)
    ledger = agent.AttemptLedger(1)
    a = approval(agent, p, ledger)
    result = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "--check", "scripts/qros_agent.py"],
        approval=a, ledger=ledger,
    )
    assert result.receipt is not None
    receipt = result.receipt
    assert receipt.task_contract_sha256
    assert receipt.budget_id == ledger.budget_id
    assert receipt.proposal_id == agent.proposal_id(p)
    assert receipt.governed_action == ("ruff", "format")
    assert receipt.command == ("ruff", "format", "--check", "scripts/qros_agent.py")
    assert receipt.pre_execution_sha
    assert receipt.approval == a
    assert receipt.returncode == 0
    assert receipt.post_execution_status == "EXECUTED"
    assert receipt.next_boundary == "complete"


def test_execution_failure_still_consumes_attempt_and_records_receipt() -> None:
    agent = load_agent()
    p = proposal(agent)
    ledger = agent.AttemptLedger(2)
    a = approval(agent, p, ledger)
    failed = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "--unknown-option", "scripts/qros_agent.py"],
        approval=a, ledger=ledger,
    )
    assert failed.status == "FAILED"
    assert failed.receipt is not None
    assert failed.receipt.attempt_number == 1
    assert failed.receipt.returncode != 0
    assert ledger.consumed_attempts == 1


def test_unapproved_proposal_stops() -> None:
    agent = load_agent()
    p = dict(proposal(agent), allowed=False)
    ledger = agent.AttemptLedger(1)
    a = approval(agent, p, ledger)
    result = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "--check", "scripts/qros_agent.py"],
        approval=a, ledger=ledger,
    )
    assert result.status == "STOP"
    assert "not authorized" in result.stderr


def test_dirty_worktree_blocks_governed_execution(monkeypatch) -> None:
    agent = load_agent()
    p = proposal(agent)
    ledger = agent.AttemptLedger(1)
    a = approval(agent, p, ledger)
    monkeypatch.setattr(agent, "_git_status", lambda: (True, " M scripts/qros_agent.py\n"))
    result = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "--check", "scripts/qros_agent.py"],
        approval=a, ledger=ledger,
    )
    assert result.status == "STOP"
    assert "not clean" in result.stderr
    assert result.receipt is None
    assert result.pre_execution_sha is None
    assert ledger.consumed_attempts == 0


def test_unavailable_worktree_state_blocks_governed_execution(monkeypatch) -> None:
    agent = load_agent()
    p = proposal(agent)
    ledger = agent.AttemptLedger(1)
    a = approval(agent, p, ledger)
    monkeypatch.setattr(agent, "_git_status", lambda: (False, ""))
    result = agent.execute_proposal(
        CONTRACT, p, ["ruff", "format", "--check", "scripts/qros_agent.py"],
        approval=a, ledger=ledger,
    )
    assert result.status == "STOP"
    assert "could not establish repository worktree state" in result.stderr
    assert result.receipt is None
    assert ledger.consumed_attempts == 0
