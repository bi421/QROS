#!/usr/bin/env python3
"""Verify that every repository migration exists in the target migration history."""
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
        ["psql", db_url, "-At", "-c",
         "SELECT version::text FROM supabase_migrations.schema_migrations ORDER BY version"],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    if p.returncode != 0:
        print(p.stderr.strip(), file=sys.stderr)
        return p.returncode

    remote = [line.strip() for line in p.stdout.splitlines() if line.strip()]
    missing = sorted(set(local) - set(remote))
    unexpected = sorted(set(remote) - set(local))
    if missing:
        print("MISSING MIGRATIONS:", ", ".join(missing), file=sys.stderr)
        return 1
    if unexpected:
        print("UNEXPECTED REMOTE MIGRATIONS:", ", ".join(unexpected), file=sys.stderr)
        return 1

    print(f"Migration parity PASS: {len(local)} migrations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
