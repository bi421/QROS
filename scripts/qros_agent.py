#!/usr/bin/env python3
"""Run the deterministic, proposal-only QROS engineering-agent control plane."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
VALIDATOR = SCRIPTS_DIR / "validate_task_contract.py"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@dataclass(frozen=True)
class AgentDecision:
    status: str
    task_contract: dict[str, Any]
    classification: dict[str, Any]
    proposal: dict[str, Any]
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
