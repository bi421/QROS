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
MIGRATIONS = ROOT / "supabase" / "migrations"

def run(label: str, command: list[str], *, env: dict[str, str] | None = None) -> dict[str, object]:
    p = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    return {
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
    command = [
        "psql", url, "-At", "-F", "\t", "-c",
        "SELECT dataset_id::text || E'\\t' || version_no::text || E'\\t' || "
        "COALESCE(content_sha256::text, '') FROM public.dataset_version "
        "ORDER BY dataset_id, version_no",
    ]
    p = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
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

def apply_migrations_fallback(target: str) -> dict[str, object]:
    # fallback: psql-ээр бүх migration-ууд шууд түрхэх
    for sql_file in sorted(MIGRATIONS.glob("*.sql")):
        p = subprocess.run(["psql", target, "-f", str(sql_file)], cwd=ROOT, text=True, capture_output=True, check=False)
        if p.returncode!= 0:
            return {
                "label": "apply_migrations_fallback",
                "command": ["psql", target, "-f", str(sql_file)],
                "returncode": p.returncode,
                "status": "FAIL",
                "stdout": p.stdout[-5000:],
                "stderr": p.stderr[-5000:] + f"\nFailed file: {sql_file.name}",
            }
    return {
        "label": "apply_migrations_fallback",
        "command": ["psql", target, "apply all migrations via psql"],
        "returncode": 0,
        "status": "PASS",
        "stdout": "fallback psql apply PASS",
        "stderr": "",
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db-url", required=True)
    parser.add_argument("--admin-db-url", required=True)
    parser.add_argument("--report", default=".health/backup_verify.json")
    parser.add_argument("--object-before", type=Path)
    parser.add_argument("--object-after", type=Path)
    parser.add_argument("--keep-target", action="store_true")
    args = parser.parse_args()

    if not all(shutil.which(x) for x in ("pg_dump", "pg_restore", "createdb", "dropdb", "psql", "supabase")):
        missing = [x for x in ("pg_dump", "pg_restore", "createdb", "dropdb", "psql", "supabase") if not shutil.which(x)]
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
    dump = ROOT / ".health" / f"{target_name}.dump"
    dump.parent.mkdir(parents=True, exist_ok=True)

    try:
        before = sql_hash(args.source_db_url)
        report["dataset_hash_before"] = before
        report["storage_hash_before"] = object_hash(args.object_before)

        steps = []
        # 1. Эхлээд target DB үүсгэ
        steps.append(run("create_target_db", ["createdb", "--maintenance-db", args.admin_db_url, target_name]))
        if steps[-1]["status"]!= "PASS":
            report["checks"] = {str(s["label"]): s for s in steps}
            return write_report(report, args.report)

        # 2. Migrations түрхэх - supabase оролд, бүтэлгүйтвэл psql fallback
        push = run("apply_all_migrations", ["supabase", "db", "push", "--db-url", target, "--include-all"])
        steps.append(push)
        if push["status"]!= "PASS":
            up = run("apply_migrations_up", ["supabase", "migration", "up", "--db-url", target])
            steps.append(up)
            if up["status"]!= "PASS":
                fb = apply_migrations_fallback(target)
                steps.append(fb)
                if fb["status"]!= "PASS":
                    report["checks"] = {str(s["label"]): s for s in steps}
                    return write_report(report, args.report)

        # 3. Migration parity шалгах (одоо robust болсон)
        steps.append(run("verify_migrations", [sys.executable, str(ROOT / "scripts" / "verify_migrations.py")], env={**os.environ, "QROS_VERIFY_DATABASE_URL": target}))

        # 4. Data dump / restore - schema аль хэдийнэ байгаа тул data-only зөв
        steps.append(run("pg_dump", ["pg_dump", "--format=custom", "--data-only", "--schema=public", "--no-owner", "--no-acl", "--file", str(dump), args.source_db_url]))
        steps.append(run("restore_data", ["pg_restore", "--data-only", "--no-owner", "--no-acl", "--dbname", target, str(dump)]))

        report["checks"] = {str(step["label"]): step for step in steps}
        if any(step["status"]!= "PASS" for step in steps):
            return write_report(report, args.report)

        after = sql_hash(target)
        report["dataset_hash_after"] = after
        report["dataset_hash_match"] = before == after
        tenant = run("tenant_isolation", ["supabase", "test", "db", "supabase/tests/tenant_isolation_test.sql", "--db-url", target])
        report["checks"]["tenant_isolation"] = tenant
        report["storage_hash_after"] = object_hash(args.object_after)
        if args.object_before and args.object_after:
            report["storage_hash_match"] = report["storage_hash_before"] == report["storage_hash_after"]

        passed = (
            report["dataset_hash_match"] is True
            and tenant["status"] == "PASS"
            and (not args.object_before or not args.object_after or report["storage_hash_match"] is True)
        )
        report["status"] = "PASS" if passed else "FAIL"
        return write_report(report, args.report)
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        return write_report(report, args.report)
    finally:
        if not args.keep_target:
            subprocess.run(["dropdb", "--if-exists", "--maintenance-db", args.admin_db_url, target_name], cwd=ROOT, text=True, capture_output=True, check=False)
        dump.unlink(missing_ok=True)

def write_report(report: dict[str, object], path: str) -> int:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
