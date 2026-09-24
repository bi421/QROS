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
    vers = []
    for p in MIGRATIONS.glob("*.sql"):
        m = VERSION_RE.match(p.name)
        if m:
            vers.append(m.group(1))
    return sorted(vers)

def get_remote_via_psql(db_url: str) -> list[str]:
    queries = [
        "SELECT version FROM supabase_migrations.history ORDER BY version",
        "SELECT version FROM supabase_migrations.schema_migrations ORDER BY version",
    ]
    for q in queries:
        proc = subprocess.run(["psql", db_url, "-At", "-c", q], text=True, capture_output=True, check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            found = re.findall(r"\b\d{10,}\b", proc.stdout)
            if found:
                return sorted(set(found))
    return []

def parse_cli_output(output: str) -> list[tuple[str, str]]:
    norm = output.replace("│", "|").replace("┃", "|").replace("â”‚", "|").replace("â”", "|")
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
    # Explicit target wins. For local verification, fall back to DATABASE_URL
    # and finally the canonical Supabase local Postgres endpoint. This keeps
    # migration verification usable without putting database credentials in
    # .env; production/DR callers still pass an explicit target URL.
    db_url = (
        os.environ.get("QROS_VERIFY_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    )

    local = get_local_versions()
    if not local:
        print("No SQL migrations found", file=sys.stderr)
        return 2

    p = subprocess.run(["supabase", "migration", "list", "--db-url", db_url], cwd=ROOT, text=True, capture_output=True, check=False)
    cli_out = p.stdout + "\n" + p.stderr
    rows = parse_cli_output(cli_out)

    if not rows:
        remote = get_remote_via_psql(db_url)
        if remote:
            rows = [(v, v) for v in remote]

    if not rows:
        print("migration list contained no parseable migration rows", file=sys.stderr)
        print(cli_out[-2000:], file=sys.stderr)
        fallback = get_remote_via_psql(db_url)
        print(f"psql fallback found {len(fallback)} versions", file=sys.stderr)
        return 2

    mismatches = [(lv, rv) for lv, rv in rows if lv!= rv]
    if mismatches:
        for lv, rv in mismatches:
            print(f"MIGRATION MISMATCH: local={lv} remote={rv}", file=sys.stderr)
        return 1

    applied = [rv for _, rv in rows]
    if sorted(applied)!= sorted(local):
        psql_remote = get_remote_via_psql(db_url)
        if sorted(psql_remote) == sorted(local):
            print(f"Migration parity PASS (via psql fallback): {len(local)} migrations")
            return 0
        print("MIGRATION MISMATCH: history does not match repository", file=sys.stderr)
        return 1

    print(f"Migration parity PASS: {len(local)} migrations")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
