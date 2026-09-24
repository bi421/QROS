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

def get_local_versions():
    return sorted(match.group(1) for path in MIGRATIONS.glob("*.sql") if (m := VERSION_RE.match(path.name)))

def get_remote_via_psql(db_url: str) -> list[str]:
    queries = [
        "SELECT version FROM supabase_migrations.history ORDER BY version",
        "SELECT version FROM supabase_migrations.schema_migrations ORDER BY version",
    ]
    for q in queries:
        p = subprocess.run(["psql", db_url, "-At", "-c", q], text=True, capture_output=True, check=False)
        if p.returncode == 0 and p.stdout.strip():
            vers = re.findall(r"\b\d{10,}\b", p.stdout)
            if vers:
                return sorted(set(vers))
    return []

def parse_cli_output(output: str) -> list[tuple[str, str]]:
    # normalize box drawing
    norm = output.replace("│", "|").replace("┃", "|").replace("â”‚", "|").replace("â”", "|").replace("Â", "")
    rows: list[tuple[str, str]] = []
    for raw in norm.splitlines():
        line = raw.strip()
        if not line:
            continue
        vers = re.findall(r"\b\d{10,}\b", line)
        if len(vers) >= 2:
            rows.append((vers[0], vers[1]))
        elif len(vers) == 1 and "|" in line:
            cols = [c.strip() for c in line.split("|")]
            digit_cols = [c for c in cols if re.fullmatch(r"\d{10,}", c)]
            if len(digit_cols) >= 2:
                rows.append((digit_cols[0], digit_cols[1]))
            elif len(digit_cols) == 1:
                rows.append((digit_cols[0], digit_cols[0]))
    return rows

def main() -> int:
    db_url = os.environ.get("QROS_VERIFY_DATABASE_URL")
    if not db_url:
        print("QROS_VERIFY_DATABASE_URL is required", file=sys.stderr)
        return 2

    local = get_local_versions()
    if not local:
        print("No SQL migrations found", file=sys.stderr)
        return 2

    p = subprocess.run(["supabase", "migration", "list", "--db-url", db_url], cwd=ROOT, text=True, capture_output=True, check=False)
    cli_stdout = p.stdout + "\n" + p.stderr

    rows = parse_cli_output(cli_stdout)
    if not rows:
        # fallback to psql
        remote = get_remote_via_psql(db_url)
        if remote:
            rows = [(v, v) for v in remote]

    if not rows:
        print("migration list contained no parseable migration rows", file=sys.stderr)
        print("--- supabase migration list output ---", file=sys.stderr)
        print(cli_stdout[-2000:], file=sys.stderr)
        # try psql list for debug
        psql_remote = get_remote_via_psql(db_url)
        print(f"psql fallback found {len(psql_remote)} versions: {psql_remote[:10]}", file=sys.stderr)
        return 2

    mismatches = [(lv, rv) for lv, rv in rows if not lv or not rv or lv!= rv]
    if mismatches:
        for lv, rv in mismatches:
            print(f"MIGRATION MISMATCH: local={lv or '<none>'} remote={rv or '<none>'}", file=sys.stderr)
        return 1

    applied = [rv for _, rv in rows]
    # allow extra remote that are not in local? No, exact match required
    if sorted(applied)!= sorted(local):
        # try psql exact check as well
        psql_remote = get_remote_via_psql(db_url)
        if sorted(psql_remote) == sorted(local):
            print(f"Migration parity PASS (via psql fallback): {len(local)} migrations")
            return 0
        print("MIGRATION MISMATCH: parsed applied history does not exactly match repository migration versions", file=sys.stderr)
        print(f"local {len(local)}: {local[-5:]}", file=sys.stderr)
        print(f"remote {len(applied)}: {applied[-5:]}", file=sys.stderr)
        return 1

    print(f"Migration parity PASS: {len(local)} migrations")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
