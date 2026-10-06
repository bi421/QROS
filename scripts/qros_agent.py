#!/usr/bin/env python3
"""Run the deterministic, proposal-only QROS engineering-agent control plane."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
VALIDATOR = SCRIPTS_DIR / "validate_task_contract.py"
EXECUTABLES = frozenset({"ruff"})
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
class ExecutionResult:
    status: str
    command: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    diff: str
    next_boundary: str


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
) -> ExecutionResult:
    return ExecutionResult(
        status,
        argv,
        returncode,
        stdout,
        stderr,
        diff,
        next_boundary,
    )


def execute_proposal(
    task_contract: Path,
    proposal: dict[str, object],
    command: Sequence[str],
    *,
    approved: bool = False,
    attempt_limit: int = 1,
) -> ExecutionResult:
    argv = tuple(command)

    if proposal.get("allowed") is not True:
        return _result(
            "STOP",
            argv,
            None,
            stderr="proposal is not authorized for execution",
        )

    allowed_paths = _allowed_paths_from_contract(task_contract)
    if not allowed_paths:
        return _result(
            "STOP",
            argv,
            None,
            stderr="task contract has no executable allowed paths",
        )

    if attempt_limit < 1:
        return _result(
            "STOP",
            argv,
            None,
            stderr="attempt limit exhausted",
        )

    if not argv or Path(argv[0]).name not in EXECUTABLES:
        return _result(
            "STOP",
            argv,
            None,
            stderr="command is outside governed allowlist",
        )

    if any(any(char in token for char in SHELL_META) for token in argv):
        return _result(
            "STOP",
            argv,
            None,
            stderr="shell metacharacters are forbidden",
        )

    governed_action = proposal.get("governed_action")
    if (
        not isinstance(governed_action, list)
        or len(governed_action) != 2
        or not all(isinstance(item, str) for item in governed_action)
    ):
        return _result(
            "STOP",
            argv,
            None,
            stderr="proposal is missing a governed action",
        )
    if len(argv) < 2 or tuple(argv[:2]) != tuple(governed_action):
        return _result(
            "STOP",
            argv,
            None,
            stderr="command does not match governed proposal action",
        )
    if tuple(governed_action) not in {("ruff", "check"), ("ruff", "format")}:
        return _result(
            "STOP",
            argv,
            None,
            stderr="governed proposal action is outside allowlist",
        )

    roots = tuple(path.resolve() for path in allowed_paths)
    paths = tuple(Path(token).resolve() for token in argv[2:])
    if not paths or any(
        not any(path == root or root in path.parents for root in roots)
        for path in paths
    ):
        return _result(
            "STOP",
            argv,
            None,
            stderr="command path escapes task scope",
        )

    if not approved:
        return _result(
            "DRY_RUN",
            argv,
            None,
            next_boundary="human-approval",
        )

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
        )

    return _result(
        "EXECUTED" if result.returncode == 0 else "FAILED",
        argv,
        result.returncode,
        result.stdout,
        result.stderr,
        diff,
        "complete" if result.returncode == 0 else "human-review",
    )


def run(task_contract: Path, log: str, attempt_limit: int) -> AgentDecision:
    valid, validation_output = validate_task_contract(task_contract)
    task_result = {
        "path": str(task_contract),
        "valid": valid,
        "evidence": validation_output,
    }
    if not valid:
        return AgentDecision(
            "STOP",
            task_result,
            {
                "category": "ambiguous/unsafe",
                "repairable": False,
                "evidence": ["invalid task contract"],
            },
            {
                "action": "stop",
                "allowed": False,
                "attempt_limit": attempt_limit,
            },
            "human-review",
        )

    classification = classify(log)
    proposal = propose(classification, attempt_limit)
    status = "PROPOSAL_READY" if proposal["allowed"] else "STOP"
    next_boundary = "governed-executor" if proposal["allowed"] else "human-review"
    return AgentDecision(
        status,
        task_result,
        classification,
        proposal,
        next_boundary,
    )


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

    log = args.ci_log.read_text(encoding="utf-8")
    decision = run(args.task_contract, log, args.attempt_limit)
    print(json.dumps(asdict(decision), sort_keys=True))
    return 0 if decision.status != "STOP" else 2


if __name__ == "__main__":
    raise SystemExit(main())
