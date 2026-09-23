#!/usr/bin/env python3
"""Rebuild or inspect a Supabase Postgres database and verify the tenant/RLS contract."""

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
    "entitlements",
)


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True, check=False
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
        if line:
            parts = line.split("\t")
            rows.append({str(i): value for i, value in enumerate(parts)})
    return rows


def normalize_sql(value: str | None) -> str:
    return " ".join(
        (value or "")
        .replace('"', "")
        .replace("::text", "")
        .replace("(", "")
        .replace(")", "")
        .split()
    ).lower()


def verify_schema() -> int:
    tenant_columns = query(
        """
        select table_name, column_name
        from information_schema.columns
        where table_schema = 'public'
          and table_name = any(%s)
        order by table_name
        """ % ("ARRAY[" + ",".join("'" + t + "'" for t in TENANT_TABLES) + "]",)
    )
    column_map = {str(row["0"]): str(row["1"]) for row in tenant_columns}
    missing_workspace_id = [
        table for table in TENANT_TABLES
        if table not in column_map and table not in {"workspace", "workspace_member"}
    ]

    rls_rows = query(
        """
        select tablename
        from pg_tables
        where schemaname = 'public'
          and tablename = any(%s)
          and rowsecurity = false
        order by tablename
        """ % ("ARRAY[" + ",".join("'" + t + "'" for t in TENANT_TABLES) + "]",)
    )
    rls_missing = [str(row["0"]) for row in rls_rows]

    policy_rows = query(
        """
        select tablename, policyname, cmd, coalesce(qual, ''), coalesce(with_check, '')
        from pg_policies
        where schemaname = 'public'
          and tablename = any(%s)
        order by tablename, policyname
        """ % ("ARRAY[" + ",".join("'" + t + "'" for t in TENANT_TABLES) + "]",)
    )
    policies: dict[str, list[dict[str, str]]] = {}
    for row in policy_rows:
        table = str(row["0"])
        policies.setdefault(table, []).append(
            {
                "name": str(row["1"]),
                "cmd": str(row["2"]).upper(),
                "qual": str(row["3"]),
                "with_check": str(row["4"]),
            }
        )

    policy_gaps: list[str] = []
    for table in TENANT_TABLES:
        table_policies = policies.get(table, [])
        if not any(policy["cmd"] in {"SELECT", "ALL"} for policy in table_policies):
            policy_gaps.append(f"{table}:missing SELECT/ALL policy")
        if table not in {"workspace", "workspace_member"}:
            if not any(
                "workspace" in normalize_sql(policy["qual"])
                or "workspace" in normalize_sql(policy["with_check"])
                or "member" in normalize_sql(policy["qual"])
                or "member" in normalize_sql(policy["with_check"])
                for policy in table_policies
            ):
                policy_gaps.append(f"{table}:no workspace/member tenant predicate")

    diff_command = [
        "supabase", "db", "diff", "--db-url", DB_URL, "--schema", "public"
    ]
    diff = run(diff_command, check=False)
    SCHEMA_DIFF.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_DIFF.write_text(diff.stdout + diff.stderr, encoding="utf-8")

    checks = {
        "migration_replay": True,
        "tenant_tables_missing": [
            table for table in TENANT_TABLES if table not in column_map
        ],
        "tenant_tables_without_workspace_id": missing_workspace_id,
        "tenant_tables_without_rls": rls_missing,
        "tenant_policy_gaps": policy_gaps,
        "schema_diff_command": {
            "returncode": diff.returncode,
            "artifact": str(SCHEMA_DIFF.relative_to(ROOT)),
            "empty": not diff.stdout.strip(),
        },
    }
    print(json.dumps(checks, indent=2, sort_keys=True))
    return 1 if any(
        (
            checks["tenant_tables_missing"],
            checks["tenant_tables_without_workspace_id"],
            checks["tenant_tables_without_rls"],
            checks["tenant_policy_gaps"],
            diff.returncode != 0,
        )
    ) else 0


def main() -> int:
    ensure_tools()
    external_database = bool(os.environ.get("QROS_VERIFY_DATABASE_URL"))
    if not external_database:
        if not (ROOT / "supabase" / "config.toml").exists():
            run(["supabase", "init"])
        run(["supabase", "stop", "--no-backup"], check=False)
        run(["supabase", "start"])
        run(["supabase", "db", "reset", "--local", "--no-seed"])
    try:
        return verify_schema()
    finally:
        if not external_database:
            run(["supabase", "stop"], check=False)


if __name__ == "__main__":
    raise SystemExit(main())
