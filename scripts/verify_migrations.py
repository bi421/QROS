#!/usr/bin/env python3
"""Rebuild a fresh Supabase Postgres database and verify the tenant/RLS schema contract."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_URL = os.environ.get(
    "QROS_VERIFY_DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
)
SCHEMA_DIFF = ROOT / ".migration-audit" / "schema_diff.sql"

TENANT_TABLES = (
    "workspace",
    "workspace_member",
    "subscription",
    "dataset",
    "dataset_version",
    "research_run",
    "artifact",
    "evidence",
    "usage_event",
    "audit_log",
    "billing_event",
    "api_idempotency",
    "research_claim",
    "research_validation",
    "research_finding",
    "research_run_result",
    "research_run_artifact",
    "audit_event",
    "retention_deletion_operation",
    "workspace_retention_policy",
    "tenant_deletion_tombstone",
)

EXPECTED_POLICIES = {
    "tenant_select": ("SELECT", "USING"),
    "tenant_insert": ("INSERT", "WITH CHECK"),
    "tenant_update": ("UPDATE", "BOTH"),
    "tenant_delete": ("DELETE", "USING"),
}

TENANT_PREDICATE = "auth.jwt() ->> 'tenant_id' = tenant_id::text"


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout={result.stdout[-4000:]}\nstderr={result.stderr[-4000:]}"
        )
    return result


def ensure_tools() -> None:
    for executable in ("supabase", "psql"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"required executable not found: {executable}")


def query(sql: str) -> list[dict[str, str | None]]:
    result = run(["psql", DB_URL, "-X", "-At", "-F", "\t", "-c", sql])
    rows: list[dict[str, str | None]] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        rows.append({str(index): value for index, value in enumerate(parts)})
    return rows


def normalize_sql(value: str | None) -> str:
    return " ".join((value or "").replace('"', "").split()).lower()


def main() -> int:
    ensure_tools()
    SCHEMA_DIFF.parent.mkdir(parents=True, exist_ok=True)

    # A clean local reset is the authoritative migration replay mechanism.
    # It recreates local Postgres and applies every migration in timestamp order.
    if not (ROOT / "supabase" / "config.toml").exists():
        run(["supabase", "init"])
    run(["supabase", "stop", "--no-backup"], check=False)
    run(["supabase", "start"])
    try:
        run(["supabase", "db", "reset", "--local", "--no-seed"])

        tenant_columns = query(
            """
            select table_name, column_name
            from information_schema.columns
            where table_schema = 'public'
              and column_name = 'tenant_id'
              and data_type = 'uuid'
            order by table_name
            """
        )
        tenant_column_tables = {row["0"] for row in tenant_columns}

        missing_tenant_id = [
            table for table in TENANT_TABLES if table not in tenant_column_tables
        ]

        rls_rows = query(
            """
            select tablename, rowsecurity::text
            from pg_tables
            where schemaname = 'public'
              and rowsecurity = false
              and tablename in (
                'workspace','workspace_member','subscription','dataset',
                'dataset_version','research_run','artifact','evidence',
                'usage_event','audit_log','billing_event','api_idempotency',
                'research_claim','research_validation','research_finding',
                'research_run_result','research_run_artifact','audit_event',
                'retention_deletion_operation','workspace_retention_policy',
                'tenant_deletion_tombstone'
              )
            order by tablename
            """
        )
        rls_missing = [row["0"] for row in rls_rows]

        dataset_rls_rows = query(
            """
            select tablename
            from pg_tables
            where schemaname = 'public'
              and rowsecurity = false
              and tablename like '%dataset%'
            order by tablename
            """
        )
        dataset_rls_missing = [row["0"] for row in dataset_rls_rows]

        policy_rows = query(
            """
            select tablename, policyname, cmd,
                   coalesce(qual, ''), coalesce(with_check, '')
            from pg_policies
            where schemaname = 'public'
              and tablename = any(array[
                'workspace','workspace_member','subscription','dataset',
                'dataset_version','research_run','artifact','evidence',
                'usage_event','audit_log','billing_event','api_idempotency',
                'research_claim','research_validation','research_finding',
                'research_run_result','research_run_artifact','audit_event',
                'retention_deletion_operation','workspace_retention_policy',
                'tenant_deletion_tombstone'
              ])
            order by tablename, policyname
            """
        )
        policy_gaps: list[str] = []
        by_table: dict[str, dict[str, dict[str, str]]] = {}
        for row in policy_rows:
            table = str(row["0"])
            name = str(row["1"])
            by_table.setdefault(table, {})[name] = {
                "cmd": str(row["2"]),
                "qual": str(row["3"]),
                "with_check": str(row["4"]),
            }

        for table in TENANT_TABLES:
            policies = by_table.get(table, {})
            for policy_name, (cmd, _) in EXPECTED_POLICIES.items():
                policy = policies.get(policy_name)
                if policy is None:
                    policy_gaps.append(f"{table}.{policy_name}:missing")
                    continue
                if policy["cmd"].upper() != cmd:
                    policy_gaps.append(
                        f"{table}.{policy_name}:cmd={policy['cmd']} expected={cmd}"
                    )
                if policy_name in {"tenant_select", "tenant_update", "tenant_delete"}:
                    if normalize_sql(policy["qual"]) != normalize_sql(TENANT_PREDICATE):
                        policy_gaps.append(f"{table}.{policy_name}:USING mismatch")
                if policy_name in {"tenant_insert", "tenant_update"}:
                    if normalize_sql(policy["with_check"]) != normalize_sql(TENANT_PREDICATE):
                        policy_gaps.append(f"{table}.{policy_name}:WITH CHECK mismatch")

        diff = run(["supabase", "db", "diff", "--local", "--schema", "public"], check=False)
        SCHEMA_DIFF.write_text(diff.stdout + diff.stderr, encoding="utf-8")

        checks = {
            "migration_replay": True,
            "tenant_tables_without_tenant_id": missing_tenant_id,
            "tenant_tables_without_rls": rls_missing,
            "dataset_like_tables_without_rls": dataset_rls_missing,
            "tenant_policy_gaps": policy_gaps,
            "schema_diff_command": {
                "returncode": diff.returncode,
                "artifact": str(SCHEMA_DIFF.relative_to(ROOT)),
                "empty": not diff.stdout.strip(),
            },
        }
        print(json.dumps(checks, indent=2, sort_keys=True))

        failed = (
            bool(missing_tenant_id)
            or bool(rls_missing)
            or bool(dataset_rls_missing)
            or bool(policy_gaps)
            or diff.returncode != 0
        )
        return 1 if failed else 0
    finally:
        run(["supabase", "stop"], check=False)


if __name__ == "__main__":
    raise SystemExit(main())
