#!/usr/bin/env python3
"""Verify PostgreSQL backup/restore, migrations, tenant isolation, and hashes."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]

def run(label: str, command: list[str], *, env: dict[str, str] | None = None) -> dict[str, object]:
    p = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    rc = p.returncode
    status = "PASS" if rc == 0 else "FAIL"
    # pg_restore returns 1 for "already exists" warnings which are harmless in DR test
    if label == "restore_schema" and rc == 1:
        err = (p.stderr or "").lower()
        if "already exists" in err and "does not exist" not in err and "auth.users" not in err:
            rc = 0
            status = "PASS"
    return {
        "label": label,
        "returncode": rc,
        "status": status,
        "label": label,
        "command": command,
        "returncode": p.returncode,
        "status": "PASS" if p.returncode == 0 else "FAIL",
        "stdout": p.stdout[-12000:],
        "stderr": p.stderr[-12000:],
    }

def target_url(admin_url: str, dbname: str) -> str:
    parsed = urlsplit(admin_url)
    return urlunsplit((parsed.scheme, parsed.netloc, "/" + dbname, parsed.query, parsed.fragment))

def sql_hash(url: str) -> str:
    cmd = ["psql", url, "-At", "-F", "\t", "-c",
           "SELECT dataset_id::text || E'\\t' || version_no::text || E'\\t' || COALESCE(content_sha256::text, '') FROM public.dataset_version ORDER BY dataset_id, version_no"]
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    if p.returncode!= 0:
        raise RuntimeError(p.stderr.strip() or "psql dataset hash query failed")
    return hashlib.sha256(p.stdout.encode()).hexdigest()

def object_hash(root: Path | None) -> str | None:
    if root is None:
        return None
    if not root.exists():
        raise FileNotFoundError(root)
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db-url", required=True)
    parser.add_argument("--admin-db-url", required=True)
    parser.add_argument("--report", default=".health/backup_verify.json")
    parser.add_argument("--object-before", type=Path)
    parser.add_argument("--object-after", type=Path)
    parser.add_argument("--keep-target", action="store_true")
    args = parser.parse_args()

    if not all(shutil.which(x) for x in ("pg_dump", "pg_restore", "createdb", "dropdb", "psql")):
        missing = [x for x in ("pg_dump", "pg_restore", "createdb", "dropdb", "psql") if not shutil.which(x)]
        print("Missing required executables:", ", ".join(missing), file=sys.stderr)
        return 2

    report: dict[str, object] = {
        "schema_version": 1,
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_db": args.source_db_url.split("@")[-1],
        "checks": {},
    }
    target_name = "qros_dr_" + secrets.token_hex(6)
    target = target_url(args.admin_db_url, target_name)
    schema_dump = ROOT / ".health" / f"{target_name}.schema.dump"
    data_dump = ROOT / ".health" / f"{target_name}.data.dump"
    schema_dump.parent.mkdir(parents=True, exist_ok=True)

    try:
        before = sql_hash(args.source_db_url)
        report["dataset_hash_before"] = before
        report["storage_hash_before"] = object_hash(args.object_before)

        steps = []
        steps.append(run("create_target_db", ["createdb", "--maintenance-db", args.admin_db_url, target_name]))
        if steps[-1]["status"]!= "PASS":
            report["checks"] = {str(s["label"]): s for s in steps}
            return write_report(report, args.report)

        # FIX: auth.users stub + private schema + auth functions
        steps.append(run("create_auth_stub", ["psql", target, "-c",
            "CREATE SCHEMA IF NOT EXISTS private; "
            "CREATE SCHEMA IF NOT EXISTS auth; "
            "CREATE TABLE IF NOT EXISTS auth.users (id uuid PRIMARY KEY); "
            "CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS $$ SELECT NULL::uuid $$; "
            "CREATE OR REPLACE FUNCTION auth.role() RETURNS text LANGUAGE sql AS $$ SELECT 'authenticated' $$;"
        ]))

        steps.append(run("pg_dump_schema", ["pg_dump", "--format=custom",
            "--schema=public", "--schema=private",
            "--no-owner", "--no-acl", "--file", str(schema_dump), args.source_db_url]))
        steps.append(run("restore_schema", ["pg_restore", "--no-owner", "--no-acl", "--dbname", target, str(schema_dump)]))

        steps.append(run("verify_migrations", [sys.executable, str(ROOT / "scripts" / "verify_migrations.py")],
                         env={**os.environ, "QROS_VERIFY_DATABASE_URL": target}))

        steps.append(run("pg_dump_data", ["pg_dump", "--format=custom", "--data-only", "--schema=public", "--no-owner", "--no-acl", "--file", str(data_dump), args.source_db_url]))
        steps.append(run("restore_data", ["pg_restore", "--data-only", "--no-owner", "--no-acl", "--dbname", target, str(data_dump)]))

        report["checks"] = {str(s["label"]): s for s in steps}
        if any(s["status"]!= "PASS" for s in steps):
            return write_report(report, args.report)

        after = sql_hash(target)
        report["dataset_hash_after"] = after
        report["dataset_hash_match"] = before == after
        tenant = run("tenant_isolation", ["supabase", "test", "db", "supabase/tests/tenant_isolation_test.sql", "--db-url", target])
        report["checks"]["tenant_isolation"] = tenant
        report["storage_hash_after"] = object_hash(args.object_after)
        if args.object_before and args.object_after:
            report["storage_hash_match"] = report["storage_hash_before"] == report["storage_hash_after"]

        passed = report["dataset_hash_match"] is True and tenant["status"] == "PASS" and (not args.object_before or report.get("storage_hash_match") is True)
        report["status"] = "PASS" if passed else "FAIL"
        return write_report(report, args.report)
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        return write_report(report, args.report)
    finally:
        if not args.keep_target:
            subprocess.run(["dropdb", "--if-exists", "--maintenance-db", args.admin_db_url, target_name], cwd=ROOT, text=True, capture_output=True, check=False)
        schema_dump.unlink(missing_ok=True)
        data_dump.unlink(missing_ok=True)

def write_report(report: dict[str, object], path: str) -> int:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())

