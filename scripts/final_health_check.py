"""Run the exact release health gate and emit health_evidence_<sha>.json."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEALTH = ROOT / ".health"

def run(name, cmd, env=None):
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expected-commit", required=True)
    ap.add_argument("--db-url", required=True)
    ap.add_argument("--source-db-url", required=True)
    ap.add_argument("--admin-db-url", required=True)
    ap.add_argument("--object-before", type=Path)
    ap.add_argument("--object-after", type=Path)
    a = ap.parse_args()

    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()

    if actual!= a.expected_commit:
        print(
            f"commit mismatch: expected {a.expected_commit}, got {actual}",
            file=sys.stderr,
        )
        return 1

    env = {**os.environ, "QROS_VERIFY_DATABASE_URL": a.db_url}
    checks = {}

    checks["tenant_isolation"] = run(
        "tenant_isolation",
        [
            "supabase",
            "test",
            "db",
            "supabase/tests/tenant_isolation_test.sql",
            "--db-url",
            a.db_url,
        ],
        env,
    )

    backup = [
        sys.executable,
        "scripts/backup_verify.py",
        "--source-db-url",
        a.source_db_url,
        "--admin-db-url",
        a.admin_db_url,
    ]
    if a.object_before and a.object_after:
        backup += [
            "--object-before",
            str(a.object_before),
            "--object-after",
            str(a.object_after),
        ]

    checks["backup_restore"] = run("backup_restore", backup, env)

    coverage = {}
    cp = ROOT / ".health" / "coverage.json"
    if cp.exists():
        coverage = json.loads(cp.read_text(encoding="utf-8")).get("totals", {})

    passed = all(c["status"] == "PASS" for c in checks.values())

    evidence = {
        "schema_version": 1,
        "commit": actual,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tests_passed": passed,
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
