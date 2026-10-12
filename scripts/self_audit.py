#!/usr/bin/env python3
"""Fail-closed repository self-audit for append-only database migrations.

The baseline is the reviewed main commit at which this audit policy was added.
New migration files are allowed; modifying, renaming, or deleting an existing
migration after that baseline fails the audit. The audit does not apply SQL.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Reviewed policy baseline: QROS main before this self-audit was introduced.
BASELINE = "c7976fa555ce5721f112bb0fb03e5b8b2e078c73"
MIGRATIONS = "supabase/migrations"


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    if not (ROOT / ".git").exists():
        print("SELF_AUDIT_FAIL: .git metadata unavailable; cannot verify history", file=sys.stderr)
        return 2

    baseline_check = git("cat-file", "-e", f"{BASELINE}^{{commit}}")
    if baseline_check.returncode != 0:
        print(
            f"SELF_AUDIT_FAIL: policy baseline {BASELINE} is missing; fetch full Git history",
            file=sys.stderr,
        )
        return 2

    ancestry = git("merge-base", "--is-ancestor", BASELINE, "HEAD")
    if ancestry.returncode != 0:
        print(
            f"SELF_AUDIT_FAIL: HEAD is not descended from reviewed baseline {BASELINE}",
            file=sys.stderr,
        )
        return 2

    changes = git(
        "diff",
        "--name-status",
        "--find-renames",
        BASELINE,
        "HEAD",
        "--",
        MIGRATIONS,
    )
    if changes.returncode != 0:
        print(f"SELF_AUDIT_FAIL: unable to inspect migration history: {changes.stderr}", file=sys.stderr)
        return 2

    violations: list[str] = []
    for line in changes.stdout.splitlines():
        fields = line.split("\t")
        status = fields[0]
        # Added migrations are forward-only and allowed. Every other change
        # to migration history (modify/delete/rename/copy/type change) is flagged.
        if status != "A":
            violations.append(line)

    if violations:
        print("SELF_AUDIT_FAIL: immutable migration history changed since policy baseline:")
        for violation in violations:
            print(f"  {violation}")
        print("Create a new forward migration; do not edit or remove an existing migration.")
        return 1

    migration_dir = ROOT / MIGRATIONS
    if not migration_dir.is_dir():
        print(f"SELF_AUDIT_FAIL: migration directory missing: {MIGRATIONS}", file=sys.stderr)
        return 2
    sql_files = sorted(migration_dir.glob("*.sql"))
    if not sql_files:
        print("SELF_AUDIT_FAIL: no SQL migrations found", file=sys.stderr)
        return 2
    duplicate_names = len({path.name for path in sql_files}) != len(sql_files)
    if duplicate_names:
        print("SELF_AUDIT_FAIL: duplicate migration filenames detected", file=sys.stderr)
        return 1

    print(
        "SELF_AUDIT_PASS: "
        f"baseline={BASELINE} head={git('rev-parse', 'HEAD').stdout.strip()} "
        f"migration_count={len(sql_files)}; no existing migration modified, renamed, or deleted"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
