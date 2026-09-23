#!/usr/bin/env python3
"""Verify QROS migration replay and SaaS RLS invariants on a fresh local database."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"
ARTIFACTS = ROOT / "artifacts"
NAME_RE = re.compile(r"^\d{12}_[a-z0-9][a-z0-9_-]*\.sql$")

TENANT_TABLES = {
    "workspace", "workspace_member", "subscription", "dataset",
    "dataset_version", "research_run", "research_run_result",
    "research_run_artifact", "artifact", "evidence", "usage_event",
    "audit_log", "api_idempotency", "api_rate_limit", "billing_event",
    "audit_event", "retention_deletion_operation", "research_claim",
    "research_validation", "research_finding",
}

SERVER_ONLY = {
    "research_run_result", "research_run_artifact", "research_validation",
    "research_finding", "api_idempotency", "api_rate_limit", "billing_event",
    "audit_event", "retention_deletion_operation",
}

RLS_QUERY = """
select coalesce(json_agg(row_to_json(x) order by relname), '[]'::json)
from (
  select c.relname, c.relrowsecurity, c.relforcerowsecurity
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and c.relkind = 'r'
    and c.relname = any(%s)
) x;
"""

POLICY_QUERY = """
select coalesce(json_agg(row_to_json(x) order by relname, polname), '[]'::json)
from (
  select c.relname, p.polname, p.polcmd,
         coalesce(pg_get_expr(p.polqual, p.polrelid), '') as using_expr,
         coalesce(pg_get_expr(p.polwithcheck, p.polrelid), '') as check_expr
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  left join pg_policy p on p.polrelid = c.oid
  where n.nspname = 'public' and c.relkind = 'r'
    and c.relname = any(%s)
) x;
"""


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=check)


def migration_integrity() -> None:
    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files:
        raise SystemExit("no Supabase migrations found")
    previous: str | None = None
    for path in files:
        if not NAME_RE.fullmatch(path.name):
            raise SystemExit(f"invalid migration filename: {path.name}")
        prefix = path.name[:12]
        if previous is not None and prefix <= previous:
            raise SystemExit(f"migration ordering is not strictly increasing: {path.name}")
        previous = prefix
        lowered = path.name.lower()
        if any(token in lowered for token in ("_down", "down_", "rollback", "revert")):
            raise SystemExit(f"down/rollback migration is forbidden: {path.name}")
        text = path.read_text(encoding="utf-8")
        if text.startswith("\ufeff"):
            raise SystemExit(f"migration contains UTF-8 BOM: {path.name}")
        if re.search(r"^\s*--\s*(down migration|rollback)\b", text, re.I | re.M):
            raise SystemExit(f"down/rollback marker is forbidden: {path.name}")
    print(f"migration integrity: PASS ({len(files)} files)")


def local_db_url() -> str:
    result = run("supabase", "status", "--output", "env")
    for line in result.stdout.splitlines():
        if line.startswith("DB_URL="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("supabase status did not expose DB_URL")


def query(db_url: str, sql: str) -> str:
    result = subprocess.run(
        ["psql", db_url, "--tuples-only", "--no-align", "--quiet",
         "-v", "ON_ERROR_STOP=1", "-c", sql],
        cwd=ROOT, text=True, capture_output=True, check=True,
    )
    return result.stdout.strip()


def sql_array() -> str:
    return "ARRAY[" + ",".join("'" + x + "'" for x in sorted(TENANT_TABLES)) + "]"


def verify_rls(db_url: str) -> None:
    rows = json.loads(query(db_url, RLS_QUERY.replace("%s", sql_array())))
    by_name = {row["relname"]: row for row in rows}
    missing = sorted(TENANT_TABLES - set(by_name))
    disabled = sorted(name for name in TENANT_TABLES if not by_name[name]["relrowsecurity"])
    not_forced = sorted(name for name in TENANT_TABLES if not by_name[name]["relforcerowsecurity"])
    if missing or disabled or not_forced:
        raise SystemExit(
            f"RLS audit failed: missing={missing}, disabled={disabled}, not_forced={not_forced}"
        )
    print(f"RLS enabled+forced: PASS ({len(TENANT_TABLES)} tenant tables)")


def verify_policies(db_url: str) -> None:
    rows = json.loads(query(db_url, POLICY_QUERY.replace("%s", sql_array())))
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row["relname"]), []).append(row)

    errors: list[str] = []
    for table in sorted(TENANT_TABLES):
        policies = grouped.get(table, [])
        if not policies:
            errors.append(f"{table}: no RLS policies")
            continue

        if table in SERVER_ONLY:
            checks = {
                "r": any(p["polcmd"] in ("r", "*") and "false" in str(p["using_expr"]).lower() for p in policies),
                "a": any(p["polcmd"] in ("a", "*") and "false" in str(p["check_expr"]).lower() for p in policies),
                "w": any(p["polcmd"] in ("w", "*") and "false" in str(p["using_expr"]).lower() and "false" in str(p["check_expr"]).lower() for p in policies),
                "d": any(p["polcmd"] in ("d", "*") and "false" in str(p["using_expr"]).lower() for p in policies),
            }
            for command, ok in checks.items():
                if not ok:
                    errors.append(f"{table}: missing fail-closed policy for {command}")
            continue

        joined = " ".join(
            str(p["using_expr"]) + " " + str(p["check_expr"]) for p in policies
        )
        if "is_workspace_member" not in joined and "auth.uid()" not in joined:
            errors.append(f"{table}: SELECT policy is not tied to auth.uid()/workspace membership")

        required = {"r": "SELECT", "a": "INSERT", "w": "UPDATE", "d": "DELETE"}
        for command, label in required.items():
            if not any(p["polcmd"] in (command, "*") for p in policies):
                errors.append(f"{table}: missing {label} policy")

    if errors:
        raise SystemExit("RLS policy audit failed:\n" + "\n".join(f"- {e}" for e in errors))
    print(f"RLS CRUD policy audit: PASS ({len(TENANT_TABLES)} tenant tables)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-reset", action="store_true")
    args = parser.parse_args()

    migration_integrity()
    if shutil.which("supabase") is None:
        raise SystemExit("supabase CLI is required")
    if shutil.which("psql") is None:
        raise SystemExit("psql is required")

    if not args.no_reset:
        run("supabase", "start")
        run("supabase", "db", "reset", "--local", "--no-seed")

    db_url = local_db_url()
    verify_rls(db_url)
    verify_policies(db_url)

    ARTIFACTS.mkdir(exist_ok=True)
    diff = run("supabase", "db", "diff", "--local", check=False)
    diff_text = diff.stdout.strip()
    (ARTIFACTS / "migration_schema_diff.sql").write_text(
        diff_text + ("\n" if diff_text else "-- No schema drift detected.\n"),
        encoding="utf-8",
    )
    if diff.returncode != 0:
        raise SystemExit(f"supabase db diff failed: {diff.stderr.strip()}")
    if diff_text and "No schema changes" not in diff_text:
        raise SystemExit("schema drift detected; see artifacts/migration_schema_diff.sql")

    print("migration replay: PASS")
    print("schema diff: CLEAN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
