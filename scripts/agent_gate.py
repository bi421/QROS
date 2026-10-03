#!/usr/bin/env python3
"""Run the canonical local gates used by autonomous QROS engineering work."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def diff_base() -> str:
    for candidate in ("origin/main", "main"):
        try:
            return git("merge-base", "HEAD", candidate)
        except subprocess.CalledProcessError:
            continue
    return "HEAD~1"


def changed_files(base: str) -> list[str]:
    commands = [
        ("diff", "--name-only", "--diff-filter=ACMR", base, "HEAD"),
        ("diff", "--name-only", "--diff-filter=ACMR"),
        ("diff", "--cached", "--name-only", "--diff-filter=ACMR"),
    ]
    files: set[str] = set()
    for command in commands:
        try:
            output = git(*command)
        except subprocess.CalledProcessError:
            continue
        files.update(line.replace("\\", "/") for line in output.splitlines() if line.strip())
    try:
        output = git("ls-files", "--others", "--exclude-standard")
        files.update(line.replace("\\", "/") for line in output.splitlines() if line.strip())
    except subprocess.CalledProcessError:
        pass
    return sorted(files)


def run(label: str, command: list[str]) -> int:
    print(f"\n=== {label} ===")
    print("$", " ".join(command))
    return subprocess.run(command, cwd=ROOT).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-contract", required=True, help="Path to the task contract")
    parser.add_argument("--profile", choices=("fast", "frozen", "full"), default="fast")
    args = parser.parse_args()

    contract = Path(args.task_contract)
    if not contract.is_absolute():
        contract = ROOT / contract
    status = run(
        "TASK CONTRACT",
        [sys.executable, "scripts/validate_task_contract.py", str(contract)],
    )
    if status:
        print("AGENT GATE: FAIL (task contract)")
        return status

    base = diff_base()
    files = changed_files(base)
    print("AGENT GATE BASE:", base)
    print("AGENT GATE CHANGED FILES:", len(files))
    for path in files:
        print(" -", path)

    if files:
        status = run("PRE-COMMIT (changed files)", ["pre-commit", "run", "--files", *files])
        if status:
            print("AGENT GATE: FAIL (pre-commit)")
            return status
    else:
        print("PRE-COMMIT: no changed files")

    status = run("PREFLIGHT", [sys.executable, "scripts/preflight.py", "--profile", args.profile])
    if status:
        print("AGENT GATE: FAIL (preflight)")
        return status

    print("AGENT GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
