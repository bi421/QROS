#!/usr/bin/env python3
"""Reject new scope creep and scratch artifacts before they enter the repository."""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_NEW_PATHS = (
    re.compile(r"(^|/)(?:_tmp|tmp_|scratch_).*", re.I),
    re.compile(r"(^|/).*\.bak$", re.I),
    re.compile(r"(^|/)(?:pytest_|ruff_).*\.txt$", re.I),
    re.compile(r"(^|/)FORENSIC_AUDIT(?:[^/]*)", re.I),
    re.compile(r"(^|/)run_full_analysis[^/]*\.py$", re.I),
)
DUPLICATE_FAMILIES = (
    ("cpp_quant", "cpp_quant_engine"),
)


def changed_paths(base: str) -> list[str]:
    completed = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return [line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args()

    try:
        paths = changed_paths(args.base)
    except subprocess.CalledProcessError as exc:
        print(f"SCOPE GUARD: FAIL: cannot compare against {args.base}: {exc.stderr.strip()}")
        return 1

    failures: list[str] = []
    for path in paths:
        for pattern in FORBIDDEN_NEW_PATHS:
            if pattern.search(path):
                failures.append(f"forbidden new artifact: {path}")
                break

    added_names = {Path(path).name.lower() for path in paths}
    if any("cpp_quant" in name for name in added_names):
        existing_cpp_quant = [p for p in paths if "cpp_quant" in p.lower()]
        if existing_cpp_quant:
            failures.append(
                "quant-engine naming requires explicit architecture review; "
                f"do not add another cpp_quant/cpp_quant_engine tree: {existing_cpp_quant}"
            )

    for family in DUPLICATE_FAMILIES:
        if any(family[0] in p.lower() and family[1] in p.lower() for p in paths):
            failures.append(f"new path contains both duplicate family names: {family}")

    workflow_dir = ROOT / ".github" / "workflows"
    for workflow in workflow_dir.glob("*.y*ml"):
        text = workflow.read_text(encoding="utf-8")
        if re.search(r"^\s*-\s*master\s*$", text, re.MULTILINE):
            failures.append(f"workflow uses forbidden master branch trigger: {workflow.as_posix()}")
        if "branches:" in text and not re.search(r"^\s*-\s*main\s*$", text, re.MULTILINE):
            failures.append(f"workflow has no explicit main trigger: {workflow.as_posix()}")

    if failures:
        print("SCOPE GUARD: FAIL")
        for failure in failures:
            print(" - " + failure)
        return 1

    print(f"SCOPE GUARD: PASS ({len(paths)} changed paths checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
