#!/usr/bin/env python3
"""Reject new scope creep and scratch artifacts before they enter the repository."""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_NEW_PATHS = (
    # Root-level Python scripts are intentionally not an allowed extension point.
    # Existing legacy files are audited separately; new/changed root scripts must
    # live under an owned directory such as scripts/ or examples/.
    re.compile(r"^[^/]+\.py$", re.I),
    re.compile(r"(^|/)(?:_tmp|tmp_|scratch_).*", re.I),
    re.compile(r"(^|/).*\.bak$", re.I),
    re.compile(r"(^|/)(?:pytest_|ruff_).*\.txt$", re.I),
    re.compile(r"(^|/)FORENSIC_AUDIT(?:[^/]*)", re.I),
    re.compile(r"(^|/)run_full_analysis[^/]*\.py$", re.I),
)


def changed_paths(base: str | None, staged: bool) -> list[str]:
    command = ["git", "diff", "--name-only", "--diff-filter=ACMR"]
    if staged:
        command.append("--cached")
    elif base:
        command.append(f"{base}...HEAD")
    else:
        command.append("HEAD")
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
    return [
        line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=None)
    parser.add_argument("--staged", action="store_true")
    args = parser.parse_args()

    try:
        paths = changed_paths(args.base, args.staged)
    except subprocess.CalledProcessError as exc:
        print(f"SCOPE GUARD: FAIL: git diff failed: {exc.stderr.strip()}")
        return 1

    failures: list[str] = []
    for path in paths:
        for pattern in FORBIDDEN_NEW_PATHS:
            if pattern.search(path):
                failures.append(f"forbidden new artifact: {path}")
                break

    for workflow in (ROOT / ".github" / "workflows").glob("*.y*ml"):
        text = workflow.read_text(encoding="utf-8")
        if re.search(r"^\s*-\s*master\s*$", text, re.MULTILINE):
            failures.append(f"workflow uses forbidden master branch trigger: {workflow.as_posix()}")
        if "branches:" in text:
            has_main = bool(
                re.search(r"^\s*-\s*main\s*$", text, re.MULTILINE)
                or re.search(r"branches:\s*\[[^]]*\bmain\b[^]]*\]", text)
            )
            if not has_main:
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
