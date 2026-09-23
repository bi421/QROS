#!/usr/bin/env python3
"""Verify that repository migrations exactly match the target migration history."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"
VERSION_RE = re.compile(r"^(\d+)_.*\.sql$")


def main() -> int:
    db_url = os.environ.get("QROS_VERIFY_DATABASE_URL")
    if not db_url:
        print("QROS_VERIFY_DATABASE_URL is required", file=sys.stderr)
        return 2

    local = sorted(
        match.group(1)
        for path in MIGRATIONS.glob("*.sql")
        if (match := VERSION_RE.match(path.name))
    )
    if not local:
        print("No SQL migrations found", file=sys.stderr)
        return 2

    p = subprocess.run(
        ["supabase", "migration", "list", "--db-url", db_url],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if p.returncode != 0:
        print(p.stderr.strip() or p.stdout.strip(), file=sys.stderr)
        return p.returncode

    rows: list[tuple[str, str]] = []
    for raw in p.stdout.splitlines():
        line = raw.replace("│", "|").strip()
        if not line or not line[:1].isdigit():
            continue
        cols = [part.strip() for part in line.split("|")]
        if len(cols) < 2:
            print("migration list format could not be parsed safely", file=sys.stderr)
            return 2
        local_version, remote_version = cols[0], cols[1]
        if local_version and not local_version.isdigit():
            continue
        if remote_version and not remote_version.isdigit():
            continue
        rows.append((local_version, remote_version))

    if not rows:
        print("migration list contained no parseable migration rows", file=sys.stderr)
        return 2

    mismatches = [
        (local_version, remote_version)
        for local_version, remote_version in rows
        if not local_version or not remote_version or local_version != remote_version
    ]
    if mismatches:
        for local_version, remote_version in mismatches:
            print(
                f"MIGRATION MISMATCH: local={local_version or '<none>'} "
                f"remote={remote_version or '<none>'}",
                file=sys.stderr,
            )
        return 1

    applied = [remote_version for _, remote_version in rows]
    if applied != local:
        print(
            "MIGRATION MISMATCH: parsed applied history does not exactly match "
            "repository migration versions",
            file=sys.stderr,
        )
        return 1

    print(f"Migration parity PASS: {len(local)} migrations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
