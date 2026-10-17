"""QROS research CLI for pre-registered hypothesis audit operations."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from researchos.orchestration.hypothesis_research import (
    HYPOTHESES,
    cost_model_ready,
    load_costs,
    register_trial,
)


def _git_sha(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def main() -> int:
    parser = argparse.ArgumentParser(prog="qros", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    research = sub.add_parser("research", help="pre-registered hypothesis research")
    research_sub = research.add_subparsers(dest="research_command", required=True)
    run = research_sub.add_parser("run", help="register and preflight a hypothesis run")
    run.add_argument("--hypothesis", required=True, choices=sorted(HYPOTHESES))
    run.add_argument("--data", default=r"C:\Users\User\Documents\XAUUSDM15.csv")
    run.add_argument("--costs", default="config/costs.yaml")
    run.add_argument("--registry", default="artifacts/trial_registry.jsonl")
    args = parser.parse_args()

    root = Path.cwd()
    data_path = Path(args.data)
    costs_path = Path(args.costs)
    if not data_path.is_file():
        parser.error(f"data file not found: {data_path}")
    if not costs_path.is_file():
        parser.error(f"cost configuration not found: {costs_path}")

    data_sha = hashlib.sha256(data_path.read_bytes()).hexdigest()
    costs = load_costs(costs_path)
    ready, missing = cost_model_ready(costs)
    record = register_trial(
        args.registry,
        hypothesis_id=args.hypothesis,
        data_sha256=data_sha,
        code_sha=_git_sha(root),
        phase="EXPLORATORY",
        metadata={
            "cost_config_sha256": hashlib.sha256(costs_path.read_bytes()).hexdigest(),
            "cost_model_ready": ready,
            "pipeline_status": "PREFLIGHT_ONLY",
        },
    )
    result = {
        "status": "PREFLIGHT_ONLY" if ready else "BLOCKED_COSTS_UNVERIFIED",
        "hypothesis": HYPOTHESES[args.hypothesis],
        "trial": record,
        "cost_model": {"ready": ready, "missing": missing},
        "holdout_policy": "This command does not read or evaluate the final 20% holdout.",
        "important": "This CLI records the pre-registered trial and validates prerequisites. It does NOT yet execute the hypothesis-specific walk-forward, negative-control, DSR/SPA, or cost-sensitivity evaluation.",
        "execution_enabled": False,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
