#!/usr/bin/env python3
"""Reject new scope creep and scratch artifacts before they enter the repository."""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_REPOSITORY_PATHS = (
    re.compile(r"^qros_pybind11_forensic_audit\\.txt$", re.I),
    re.compile(r"^scripts/cpp_true_production_v[1-9]\\.py$", re.I),
)

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


def repository_paths() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, text=False, capture_output=True, check=True
    )
    return [item for item in completed.stdout.decode("utf-8").split("\\0") if item]


def changed_paths(base: str | None, staged: bool, diff_filter: str = "ACMR") -> list[str]:
    command = ["git", "diff", "--name-only", f"--diff-filter={diff_filter}"]
    if staged:
        command.append("--cached")
    elif base:
        command.append(f"{base}...HEAD")
    else:
        command.append("HEAD")
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return [
        line.strip().replace("\\", "/")
        for line in completed.stdout.splitlines()
        if line.strip()
    ]


def is_new_native_quant_python_module(path: str) -> bool:
    """Return True for newly added Python API modules in the native Quant tree.

    The native tree is reserved for C++/nanobind implementation. Python binding
    shims and tests are legitimate there, but new Python implementation modules
    outside those areas would create another Python API surface.
    """
    parts = Path(path.replace("\\", "/")).parts
    if len(parts) < 4:
        return False
    if parts[:3] != ("researchos", "engines", "quant"):
        return False
    if not parts[-1].lower().endswith(".py"):
        return False
    remainder = parts[3:]
    if remainder and remainder[0].lower() == "python":
        return False
    if "tests" in {part.lower() for part in remainder}:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=None)
    parser.add_argument("--staged", action="store_true")
    args = parser.parse_args()

    try:
        paths = changed_paths(args.base, args.staged)
        added_paths = changed_paths(args.base, args.staged, "A")
    except subprocess.CalledProcessError as exc:
        print(f"SCOPE GUARD: FAIL: git diff failed: {exc.stderr.strip()}")
        return 1

    failures: list[str] = []

    # Changed-path rules prevent new scope creep; repository rules also detect
    # legacy forbidden artifacts that predate the current diff and would
    # otherwise escape the guard forever.
    for path in repository_paths():
        for pattern in FORBIDDEN_REPOSITORY_PATHS:
            if pattern.search(path):
                failures.append(f"forbidden repository artifact: {path}")
                break

    for path in paths:
        for pattern in FORBIDDEN_NEW_PATHS:
            if pattern.search(path):
                failures.append(f"forbidden new artifact: {path}")
                break

    for path in added_paths:
        if is_new_native_quant_python_module(path):
            failures.append(
                "forbidden new native Quant Python implementation module: "
                f"{path}"
            )

    for workflow in (ROOT / ".github" / "workflows").glob("*.y*ml"):
        text = workflow.read_text(encoding="utf-8")
        if re.search(r"^\s*-\s*master\s*$", text, re.MULTILINE):
            failures.append(
                f"workflow uses forbidden master branch trigger: {workflow.as_posix()}"
            )
        if "branches:" in text:
            has_main = bool(
                re.search(r"^\s*-\s*main\s*$", text, re.MULTILINE)
                or re.search(
                    r"branches:\s*\[[^]]*\bmain\b[^]]*\]",
                    text,
                )
            )
            if not has_main:
                failures.append(
                    f"workflow has no explicit main trigger: {workflow.as_posix()}"
                )

    if failures:
        print("SCOPE GUARD: FAIL")
        for failure in failures:
            print(" - " + failure)
        return 1

    print(f"SCOPE GUARD: PASS ({len(paths)} changed paths checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
