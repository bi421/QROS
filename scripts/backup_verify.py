#!/usr/bin/env python3
"""Verify a PostgreSQL logical backup can be restored into a disposable container.

The drill is deliberately fail-closed. It proves backup creation, restore,
required QROS schema/RLS, immutable dataset-version identity, critical
governed-record counts, and repository migration/security invariants.
It does not claim Supabase Auth/Data API, Storage, worker recovery, or RPO/RTO.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SOURCE_ENVIRONMENTS = {"local", "staging"}

def authorize_source_environment(value: str | None) -> str:
    """Require an explicit non-production recovery source authorization."""
    if not value or not value.strip():
        raise SystemExit(
            "source environment is not explicitly authorized; "
            "provide --source-environment local or staging (or "
            "QROS_BACKUP_SOURCE_ENVIRONMENT). An arbitrary database URL alone "
            "is insufficient, and --skip-restore does not make source selection safe."
        )
    environment = value.strip().lower()
    if environment == "production":
        raise SystemExit(
            "production is not an authorized source environment for backup_verify.py; "
            "this tool does not implement a production recovery path. Select an "
            "explicitly permitted non-production source instead. --skip-restore "
            "does not bypass this source gate."
        )
    if environment not in ALLOWED_SOURCE_ENVIRONMENTS:
        allowed = ", ".join(sorted(ALLOWED_SOURCE_ENVIRONMENTS))
        raise SystemExit(
            f"source environment {environment!r} is not authorized; "
            f"select one of: {allowed}. --skip-restore does not bypass this source gate."
        )
    return environment


REQUIRED_TABLES = (
    "workspace", "workspace_member", "dataset", "dataset_version",
    "research_claim", "research_run", "research_run_result",
    "research_run_artifact", "artifact", "evidence", "research_validation",
    "research_finding", "audit_event",
)
CRITICAL_COUNT_TABLES = (
    "research_claim", "research_run", "research_run_result",
    "research_run_artifact", "evidence", "artifact",
    "research_validation", "research_finding",
)


def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def psql(url: str, sql: str) -> str:
    return run(
        ["psql", url, "-At", "-F", "\t", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True,
    ).stdout.strip()


def require_tools(names: tuple[str, ...]) -> None:
    for tool in names:
        if shutil.which(tool) is None:
            raise SystemExit(f"{tool} is required")


def database_snapshot(url: str) -> dict[str, object]:
    quoted = ",".join("'" + table + "'" for table in REQUIRED_TABLES)
    tables = psql(
        url,
        f"""
        select c.relname from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind = 'r'
          and c.relname = any(ARRAY[{quoted}])
        order by c.relname
        """,
    ).splitlines()
    expected = sorted(REQUIRED_TABLES)
    if sorted(tables) != expected:
        raise SystemExit(
            "required schema mismatch: "
            f"missing={sorted(set(expected) - set(tables))}"
        )

    rls = psql(
        url,
        """
        select c.relname || '=' || case when c.relrowsecurity
               then 'enabled' else 'disabled' end
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind = 'r'
          and c.relname in (
            'workspace','workspace_member','dataset','dataset_version',
            'research_claim','research_run','research_run_result',
            'research_run_artifact','artifact','evidence','research_validation',
            'research_finding','audit_event'
          )
        order by c.relname
        """,
    ).splitlines()
    expected_rls = [f"{table}=enabled" for table in expected]
    if rls != expected_rls:
        raise SystemExit(f"RLS verification failed: {rls}")

    dataset_versions = psql(
        url,
        """
        select id::text, dataset_id::text, version_no::text, content_sha256
        from public.dataset_version order by id
        """,
    ).splitlines()

    counts = {
        table: int(psql(url, f"select count(*) from public.{table}") or "0")
        for table in CRITICAL_COUNT_TABLES
    }
    return {
        "required_tables": expected,
        "rls": rls,
        "dataset_versions": dataset_versions,
        "critical_counts": counts,
    }


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("QROS_BACKUP_DATABASE_URL"))
    parser.add_argument(
        "--source-environment",
        default=os.getenv("QROS_BACKUP_SOURCE_ENVIRONMENT"),
        help="Explicit recovery source: local or staging; production is not supported.",
    )
    parser.add_argument(
        "--source-project-ref",
        default=os.getenv("QROS_SOURCE_PROJECT_REF"),
    )
    parser.add_argument(
        "--source-release-sha",
        default=os.getenv("QROS_SOURCE_RELEASE_SHA") or os.getenv("GITHUB_SHA"),
    )
    parser.add_argument(
        "--evidence-id",
        default=os.getenv("QROS_DR_EVIDENCE_ID"),
    )
    parser.add_argument("--output", type=Path, default=Path("backup/qros.dump"))
    parser.add_argument("--report", type=Path, default=Path("backup/qros_restore_report.json"))
    parser.add_argument("--skip-restore", action="store_true")
    args = parser.parse_args()

    source_environment = authorize_source_environment(args.source_environment)
    if not args.database_url:
        raise SystemExit("QROS_BACKUP_DATABASE_URL or --database-url is required")
    require_tools(("pg_dump", "pg_restore", "psql"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    evidence_id = args.evidence_id or f"dr-{int(time.time())}-{os.getpid()}"
    started = time.time()
    backup_started_at = utc_now()
    source_version = psql(args.database_url, "show server_version;")
    source_major = source_version.split(".")[0]
    if not source_major.isdigit():
        raise SystemExit(f"could not determine PostgreSQL major version: {source_version}")

    run(["pg_dump", "--format=custom", "--no-owner", "--file", str(args.output), args.database_url])
    backup_completed_at = utc_now()
    size = args.output.stat().st_size
    if size <= 0:
        raise SystemExit("backup is empty")
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    source = database_snapshot(args.database_url)

    report: dict[str, object] = {
        "schema_version": 3,
        "status": "BLOCKED",
        "backup": {
            "path": str(args.output),
            "bytes": size,
            "sha256": digest,
            "postgres_major": int(source_major),
            "started_at": backup_started_at,
            "completed_at": backup_completed_at,
        },
        "source_integrity": {
            "dataset_versions": len(source["dataset_versions"]),
            "critical_counts": source["critical_counts"],
        },
        "restore": {"executed": False, "verified": False},
        "migration_security": {"verified": False},
        "application_readability": "NOT_EXECUTED",
        "rpo_rto": "NOT_EXECUTED",
        "evidence_manifest": {
            "schema_version": 1,
            "evidence_id": evidence_id,
            "source": {
                "environment": source_environment,
                "project_ref": args.source_project_ref,
                "release_sha": args.source_release_sha,
                "migration_version": None,
            },
            "backup": {
                "status": "VERIFIED",
                "started_at": backup_started_at,
                "completed_at": backup_completed_at,
                "sha256": digest,
                "postgres_major": int(source_major),
            },
            "restore": {
                "status": "NOT_EXECUTED",
                "target_identity": None,
                "started_at": None,
                "completed_at": None,
            },
            "verification": {
                "required_tables": {"source": "VERIFIED", "restore": "NOT_EXECUTED"},
                "rls_security": {"source": "VERIFIED", "restore": "NOT_EXECUTED"},
                "dataset_version_integrity": {"source": "RECORDED", "restore": "NOT_EXECUTED"},
                "critical_record_counts": {"source": "RECORDED", "restore": "NOT_EXECUTED"},
                "migration_security": "NOT_EXECUTED",
                "tenant_isolation_recovery": "NOT_EXECUTED",
                "storage_recovery": "NOT_EXECUTED",
                "queue_recovery": "NOT_EXECUTED",
                "application_recovery": "NOT_EXECUTED",
            },
            "rpo_rto": {"status": "NOT_EXECUTED", "rpo_seconds": None, "rto_seconds": None},
            "operator_signoff": {"status": "NOT_RECORDED", "operator": None, "signed_at": None},
        },
    }

    if args.skip_restore:
        report["status"] = "BACKUP_ONLY"
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    require_tools(("docker",))
    name = f"qros-backup-verify-{os.getpid()}"
    port = "55432"
    restore_url = f"postgresql://postgres:qros@127.0.0.1:{port}/postgres"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
    restore_started_at = utc_now()
    report["evidence_manifest"]["restore"]["started_at"] = restore_started_at
    report["evidence_manifest"]["restore"]["target_identity"] = f"disposable-docker:{name}"
    try:
        run([
            "docker", "run", "-d", "--name", name, "-p", f"{port}:5432",
            "-e", "POSTGRES_PASSWORD=qros", f"postgres:{source_major}",
        ])
        for _ in range(60):
            if subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "postgres"],
                capture_output=True,
            ).returncode == 0:
                break
            time.sleep(1)
        else:
            raise SystemExit("temporary postgres did not become ready")

        run(["pg_restore", "--clean", "--if-exists", "--no-owner",
             "--dbname", restore_url, str(args.output)])
        report["restore"] = {"executed": True, "verified": False,
                             "postgres_major": int(source_major)}

        restored = database_snapshot(restore_url)
        if restored["dataset_versions"] != source["dataset_versions"]:
            raise SystemExit("immutable dataset-version identity mismatch after restore")
        if restored["critical_counts"] != source["critical_counts"]:
            raise SystemExit(
                "critical governed-record counts changed after restore: "
                f"source={source['critical_counts']} restored={restored['critical_counts']}"
            )

        migration_check = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "verify_migrations.py"),
             "--database-url", restore_url],
            text=True, capture_output=True, check=False,
        )
        if migration_check.returncode != 0:
            raise SystemExit(
                "restored database migration/security verification failed: "
                + (migration_check.stderr.strip() or migration_check.stdout.strip())
            )

        restore_completed_at = utc_now()
        report["restore"]["verified"] = True
        report["restore"]["dataset_versions"] = len(restored["dataset_versions"])
        report["restore"]["critical_counts"] = restored["critical_counts"]
        report["migration_security"] = {
            "verified": True, "output": migration_check.stdout.strip()
        }
        manifest = report["evidence_manifest"]
        manifest["restore"]["status"] = "VERIFIED"
        manifest["restore"]["completed_at"] = restore_completed_at
        manifest["verification"]["required_tables"]["restore"] = "VERIFIED"
        manifest["verification"]["rls_security"]["restore"] = "VERIFIED"
        manifest["verification"]["dataset_version_integrity"]["restore"] = "VERIFIED"
        manifest["verification"]["critical_record_counts"]["restore"] = "VERIFIED"
        manifest["verification"]["migration_security"] = "VERIFIED"
        report["status"] = "VERIFIED"
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)

    report["elapsed_seconds"] = round(time.time() - started, 3)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
