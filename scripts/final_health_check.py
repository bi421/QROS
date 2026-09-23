"""Run the exact release health gate and emit health_evidence_<sha>.json."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HEALTH = ROOT / ".health"


def run(name: str, cmd: list[str], env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        result = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        return {
            "name": name,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "stdout": result.stdout[-2000:],
            "stderr": result.stderr[-2000:],
            "returncode": result.returncode,
        }
    except Exception as exc:
        return {"name": name, "status": "FAIL", "error": str(exc)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expected-commit", required=True)
    ap.add_argument("--db-url", required=True)
    ap.add_argument("--source-db-url", required=True)
    ap.add_argument("--admin-db-url", required=True)
    ap.add_argument("--object-before", type=Path)
    ap.add_argument("--object-after", type=Path)
    args = ap.parse_args()

    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()

    if actual != args.expected_commit:
        print(
            f"commit mismatch: expected {args.expected_commit}, got {actual}",
            file=sys.stderr,
        )
        return 1

    env = {**os.environ, "QROS_VERIFY_DATABASE_URL": args.db_url}
    checks: dict[str, dict[str, Any]] = {}

    checks["tenant_isolation"] = run(
        "tenant_isolation",
        [
            "supabase",
            "test",
            "db",
            "supabase/tests/tenant_isolation_test.sql",
            "--db-url",
            args.db_url,
        ],
        env,
    )

    checks["authz"] = run(
        "authz",
        [sys.executable, "scripts/check_authz_coverage.py", "--db-url", args.db_url],
        env,
    )

    backup = [
        sys.executable,
        "scripts/backup_verify.py",
        "--source-db-url",
        args.source_db_url,
        "--admin-db-url",
        args.admin_db_url,
    ]
    if args.object_before and args.object_after:
        backup += [
            "--object-before",
            str(args.object_before),
            "--object-after",
            str(args.object_after),
        ]

    checks["backup_restore"] = run("backup_restore", backup, env)

    coverage: dict[str, Any] = {}
    cp = ROOT / ".health" / "coverage.json"
    if cp.exists():
        coverage = json.loads(cp.read_text(encoding="utf-8")).get("totals", {})

    tenant_pass = checks["tenant_isolation"]["status"] == "PASS"
    authz_pass = checks["authz"]["status"] == "PASS"
    backup_pass = checks["backup_restore"]["status"] == "PASS"
    passed = tenant_pass and authz_pass and backup_pass

    evidence = {
        "schema_version": 1,
        "commit": actual,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tests_passed": passed,
        "health_status": "PASS" if passed else "FAIL",
        "rls_check": tenant_pass,
        "authz_check": authz_pass,
        "tenant_isolation_check": tenant_pass,
        "health": checks,
        "coverage": coverage,
    }

    HEALTH.mkdir(parents=True, exist_ok=True)
    path = HEALTH / f"health_evidence_{actual}.json"
    path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(evidence, indent=2, sort_keys=True))
    print(f"EVIDENCE={path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
