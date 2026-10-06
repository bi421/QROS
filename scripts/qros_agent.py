#!/usr/bin/env python3
"""Run the deterministic, governed QROS engineering-agent control plane."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Sequence
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
VALIDATOR = SCRIPTS_DIR / "validate_task_contract.py"
EXECUTABLES = frozenset({"ruff"})
ALLOWED_ACTIONS = frozenset({("ruff", "check"), ("ruff", "format")})
SHELL_META = frozenset({"&", "|", ";", ">", "<", "$", "`"})

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@dataclass(frozen=True)
class AgentDecision:
    status: str
    task_contract: dict[str, Any]
    classification: dict[str, Any]
    proposal: dict[str, Any]
    next_boundary: str


@dataclass(frozen=True)
class ApprovalProvenance:
    status: str
    approver_id: str
    approved_at: str
    proposal_id: str
    governed_action: tuple[str, str]
    scope_sha256: str
    attempt_authority: str


@dataclass(frozen=True)
class ExecutionReceipt:
    receipt_id: str
    budget_id: str
    attempt_number: int
    task_contract_sha256: str
    proposal_id: str
    governed_action: tuple[str, str]
    command: tuple[str, ...]
    approval: ApprovalProvenance
    pre_execution_sha: str
    post_execution_status: str
    diff: str
    stdout: str
    stderr: str
    returncode: int | None
    next_boundary: str


class AttemptLedger:
    """Process-local persistent attempt authority for a governed execution chain."""

    def __init__(self, max_attempts: int, *, budget_id: str | None = None) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.budget_id = budget_id or str(uuid4())
        self.max_attempts = max_attempts
        self._consumed: list[str] = []
        self._lock = Lock()

    @property
    def consumed_attempts(self) -> int:
        with self._lock:
            return len(self._consumed)

    def consume(self, receipt_id: str) -> int:
        with self._lock:
            if len(self._consumed) >= self.max_attempts:
                raise RuntimeError("attempt budget exhausted")
            if receipt_id in self._consumed:
                raise RuntimeError("execution receipt replay detected")
            self._consumed.append(receipt_id)
            return len(self._consumed)


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    command: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    diff: str
    next_boundary: str
    receipt: ExecutionReceipt | None = None
    pre_execution_sha: str | None = None


def _canonical_sha(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def proposal_id(proposal: dict[str, object]) -> str:
    payload = {key: value for key, value in proposal.items() if key != "proposal_id"}
    return _canonical_sha(payload)


def _task_contract_sha256(task_contract: Path) -> str:
    return hashlib.sha256(task_contract.read_bytes()).hexdigest()


def _scope_sha256(paths: Sequence[Path]) -> str:
    return _canonical_sha(sorted(str(path.resolve().relative_to(ROOT)) for path in paths))


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def approval_for(
    proposal: dict[str, object],
    task_contract: Path,
    allowed_paths: Sequence[Path],
    *,
    ledger: AttemptLedger,
    approver_id: str,
    approved_at: str,
) -> ApprovalProvenance:
    governed_action = proposal.get("governed_action")
    if (
        not isinstance(governed_action, (list, tuple))
        or len(governed_action) != 2
        or not all(isinstance(item, str) for item in governed_action)
    ):
        raise ValueError("proposal is missing a governed action")
    return ApprovalProvenance(
        status="APPROVED",
        approver_id=approver_id,
        approved_at=approved_at,
        proposal_id=proposal_id(proposal),
        governed_action=(governed_action[0], governed_action[1]),
        scope_sha256=_scope_sha256(allowed_paths),
        attempt_authority=_canonical_sha({
            "budget_id": ledger.budget_id,
            "max_attempts": ledger.max_attempts,
            "task_contract_sha256": _task_contract_sha256(task_contract),
        }),
    )


def validate_task_contract(path: Path) -> tuple[bool, list[str]]:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output.splitlines()


def classify(log: str) -> dict[str, Any]:
    from classify_ci_failure import classify as classify_failure

    result = asdict(classify_failure(log))
    evidence = result.get("evidence")
    if isinstance(evidence, tuple):
        result["evidence"] = list(evidence)
    return result


def propose(classification: dict[str, Any], attempt_limit: int) -> dict[str, Any]:
    from propose_ci_repair import propose as propose_repair

    return asdict(propose_repair(classification, attempt_limit=attempt_limit))


def _allowed_paths_from_contract(task_contract: Path) -> tuple[Path, ...]:
    text = task_contract.read_text(encoding="utf-8")
    start = text.find("### Allowed")
    end = text.find("### Forbidden", start)
    if start < 0 or end < 0:
        return ()
    paths: list[Path] = []
    for line in text[start + len("### Allowed") : end].splitlines():
        line = line.strip()
        if line.startswith("- ") and line[2:].strip():
            value = line[2:].strip()
            if value.startswith(("scripts/", "researchos/", "docs/")):
                paths.append((ROOT / value).resolve())
    return tuple(paths)


def _git_status() -> tuple[bool, str]:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0, result.stdout


def _git_head() -> tuple[bool, str]:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0, result.stdout.strip()


def _git_diff(paths: Sequence[Path]) -> tuple[bool, str]:
    relative_paths = [str(path.resolve().relative_to(ROOT)) for path in paths]
    result = subprocess.run(
        ["git", "diff", "--", *relative_paths],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0, result.stdout if result.returncode == 0 else result.stderr


def _result(
    status: str,
    argv: tuple[str, ...],
    returncode: int | None,
    stdout: str = "",
    stderr: str = "",
    diff: str = "",
    next_boundary: str = "human-review",
    receipt: ExecutionReceipt | None = None,
    pre_execution_sha: str | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        status, argv, returncode, stdout, stderr, diff, next_boundary, receipt, pre_execution_sha
    )


def _validate_approval(
    approval: ApprovalProvenance,
    proposal: dict[str, object],
    task_contract: Path,
    allowed_paths: Sequence[Path],
    ledger: AttemptLedger,
) -> str | None:
    if approval.status != "APPROVED":
        return "approval status is not APPROVED"
    if not approval.approver_id.strip():
        return "approval approver identity is missing"
    if not approval.approved_at.strip():
        return "approval timestamp is missing"
    if approval.proposal_id != proposal_id(proposal):
        return "approval does not bind to proposal identity"
    governed_action = proposal.get("governed_action")
    if not isinstance(governed_action, list) or tuple(governed_action) != approval.governed_action:
        return "approval does not bind to governed action"
    if approval.scope_sha256 != _scope_sha256(allowed_paths):
        return "approval does not bind to task scope"
    if approval.attempt_authority != _canonical_sha({
        "budget_id": "approval-bound",
        "task_contract_sha256": _task_contract_sha256(task_contract),
    }):
        return "approval attempt authority is invalid"
    return None


def execute_proposal(
    task_contract: Path,
    proposal: dict[str, object],
    command: Sequence[str],
    *,
    approval: ApprovalProvenance | None = None,
    ledger: AttemptLedger | None = None,
) -> ExecutionResult:
    argv = tuple(command)
    if proposal.get("allowed") is not True:
        return _result("STOP", argv, None, stderr="proposal is not authorized for execution")

    allowed_paths = _allowed_paths_from_contract(task_contract)
    if not allowed_paths:
        return _result("STOP", argv, None, stderr="task contract has no executable allowed paths")

    if ledger is None:
        return _result("STOP", argv, None, stderr="persistent attempt ledger is required")

    if not argv or Path(argv[0]).name not in EXECUTABLES:
        return _result("STOP", argv, None, stderr="command is outside governed allowlist")

    if any(any(char in token for char in SHELL_META) for token in argv):
        return _result("STOP", argv, None, stderr="shell metacharacters are forbidden")

    governed_action = proposal.get("governed_action")
    if (
        not isinstance(governed_action, list)
        or len(governed_action) != 2
        or not all(isinstance(item, str) for item in governed_action)
    ):
        return _result("STOP", argv, None, stderr="proposal is missing a governed action")
    if len(argv) < 2 or tuple(argv[:2]) != tuple(governed_action):
        return _result("STOP", argv, None, stderr="command does not match governed proposal action")
    if tuple(governed_action) not in ALLOWED_ACTIONS:
        return _result("STOP", argv, None, stderr="governed proposal action is outside allowlist")

    roots = tuple(path.resolve() for path in allowed_paths)
    paths = tuple(Path(token).resolve() for token in argv[2:])
    if not paths or any(
        not any(path == root or root in path.parents for root in roots) for path in paths
    ):
        return _result("STOP", argv, None, stderr="command path escapes task scope")

    if approval is None:
        return _result(
            "STOP",
            argv,
            None,
            stderr="explicit approval provenance is required",
            next_boundary="human-review",
        )

    approval_error = _validate_approval(approval, proposal, task_contract, allowed_paths, ledger)
    if approval_error:
        return _result("STOP", argv, None, stderr=approval_error)

    clean_ok, clean_status = _git_status()
    if not clean_ok:
        return _result("STOP", argv, None, stderr="could not establish repository worktree state")
    if clean_status.strip():
        return _result(
            "STOP",
            argv,
            None,
            stderr="repository worktree is not clean before governed execution",
        )

    head_ok, pre_sha = _git_head()
    if not head_ok or not pre_sha:
        return _result("STOP", argv, None, stderr="could not establish pre-execution repository SHA")

    try:
        attempt_number = ledger.consume(
            _canonical_sha({
                "budget_id": ledger.budget_id,
                "proposal_id": proposal_id(proposal),
                "command": argv,
                "pre_execution_sha": pre_sha,
            })
        )
    except RuntimeError as exc:
        return _result("STOP", argv, None, stderr=str(exc), pre_execution_sha=pre_sha)

    result = subprocess.run(
        list(argv),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    diff_ok, diff = _git_diff(paths)
    if not diff_ok:
        return _result(
            "FAILED",
            argv,
            result.returncode,
            result.stdout,
            result.stderr,
            diff,
            receipt=ExecutionReceipt(
                str(uuid4()), ledger.budget_id, attempt_number,
                _task_contract_sha256(task_contract), proposal_id(proposal),
                (governed_action[0], governed_action[1]), argv, approval, pre_sha,
                "DIFF_FAILED", diff, result.stdout, result.stderr, result.returncode,
                "human-review",
            ),
            pre_execution_sha=pre_sha,
        )

    status = "EXECUTED" if result.returncode == 0 else "FAILED"
    receipt = ExecutionReceipt(
        str(uuid4()), ledger.budget_id, attempt_number,
        _task_contract_sha256(task_contract), proposal_id(proposal),
        (governed_action[0], governed_action[1]), argv, approval, pre_sha,
        status, diff, result.stdout, result.stderr, result.returncode,
        "complete" if result.returncode == 0 else "human-review",
    )
    return _result(
        status, argv, result.returncode, result.stdout, result.stderr, diff,
        receipt=receipt, pre_execution_sha=pre_sha,
        next_boundary=receipt.next_boundary,
    )


def run(task_contract: Path, log: str, attempt_limit: int) -> AgentDecision:
    valid, validation_output = validate_task_contract(task_contract)
    task_result = {"path": str(task_contract), "valid": valid, "evidence": validation_output}
    if not valid:
        return AgentDecision(
            "STOP", task_result,
            {"category": "ambiguous/unsafe", "repairable": False, "evidence": ["invalid task contract"]},
            {"action": "stop", "allowed": False, "attempt_limit": attempt_limit},
            "human-review",
        )
    classification = classify(log)
    proposal = propose(classification, attempt_limit)
    if proposal.get("allowed") is True:
        proposal = dict(proposal)
        proposal["proposal_id"] = proposal_id(proposal)
    status = "PROPOSAL_READY" if proposal["allowed"] else "STOP"
    next_boundary = "governed-executor" if proposal["allowed"] else "human-review"
    return AgentDecision(status, task_result, classification, proposal, next_boundary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_contract", type=Path)
    parser.add_argument("ci_log", type=Path)
    parser.add_argument("--attempt-limit", type=int, default=1)
    args = parser.parse_args()
    if args.attempt_limit < 0:
        parser.error("--attempt-limit must be non-negative")
    if not args.ci_log.is_file():
        parser.error(f"CI log not found: {args.ci_log}")
    decision = run(args.task_contract, args.ci_log.read_text(encoding="utf-8"), args.attempt_limit)
    print(json.dumps(asdict(decision), sort_keys=True))
    return 0 if decision.status != "STOP" else 2


if __name__ == "__main__":
    raise SystemExit(main())
