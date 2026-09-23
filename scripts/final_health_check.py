#!/usr/bin/env python3
"""Run exact-release gates and emit/verify SHA-scoped health evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
TENANT_TEST = ROOT / "supabase" / "tests" / "tenant_isolation_test.sql"
REQUIRED_RLS_TABLES = (
    "workspace", "workspace_member", "subscription", "dataset", "dataset_version",
    "research_run", "artifact", "evidence", "usage_event", "audit_log", "billing_event",
    "api_idempotency", "research_claim", "research_validation", "research_finding",
    "research_run_result", "research_run_artifact", "audit_event",
    "retention_deletion_operation", "workspace_retention_policy",
    "tenant_deletion_tombstone", "entitlements",
)


def run_check(label: str, command: list[str], *, env: dict[str, str] | None = None) -> dict[str, object]:
    completed = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True, check=False, env=env
    )
    return {
        "label": label,
        "command": command,
        "returncode": completed.returncode,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
    }


def git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise SystemExit("cannot resolve git HEAD")
    return result.stdout.strip()


def rls_check(database_url: str) -> dict[str, object]:
    table_list = ", ".join(f"'{name}'" for name in REQUIRED_RLS_TABLES)
    sql = f"""
select coalesce(string_agg(format('%I.%I', n.nspname, c.relname), ',' order by c.relname), '')
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind = 'r'
  and c.relname in ({table_list})
  and not c.relrowsecurity;
"""
    result = run_check("rls_check", ["psql", database_url, "-Atqc", sql])
    missing = result["stdout"].strip()
    if result["status"] == "PASS" and missing:
        result["status"] = "FAIL"
        result["returncode"] = 1
        result["stderr"] = f"RLS disabled on required tables: {missing}"
    return result


def read_coverage() -> dict[str, object]:
    path = ROOT / ".health" / "coverage.json"
    if not path.exists():
        return {"status": "FAIL", "percent_covered": None, "source": str(path)}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        percent = raw["totals"]["percent_covered"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return {"status": "FAIL", "percent_covered": None, "source": str(path)}
    if not isinstance(percent, (int, float)):
        return {"status": "FAIL", "percent_covered": None, "source": str(path)}
    return {"status": "PASS", "percent_covered": percent, "source": str(path)}


def verify_evidence(path: Path, expected_commit: str) -> None:
    if not path.is_file():
        raise SystemExit(f"required health evidence missing: {path.name}")
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid health evidence: {exc}") from exc
    if evidence.get("commit") != expected_commit:
        raise SystemExit("health evidence commit does not match current commit")
    if evidence.get("tests_passed") is not True:
        raise SystemExit("health evidence does not record tests_passed=true")
    if evidence.get("health_status") != "PASS":
        raise SystemExit("health evidence health_status is not PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--backup-source-url", required=True)
    parser.add_argument("--backup-target-admin-url", required=True)
    parser.add_argument("--object-root-before", type=Path, required=True)
    parser.add_argument("--object-root-after", type=Path, required=True)
    args = parser.parse_args()

    actual = git_sha()
    if actual != args.expected_commit or len(args.expected_commit) != 40:
        raise SystemExit(f"exact-release violation: expected {args.expected_commit}, got {actual}")

    coverage_path = ROOT / ".health" / "coverage.json"
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    checks: dict[str, dict[str, object]] = {}

    checks["ruff"] = run_check("ruff", [sys.executable, "-m", "ruff", "check", "."])
    checks["mypy"] = run_check("mypy", [sys.executable, "-m", "mypy", "."])
    checks["pytest_real_db"] = run_check(
        "pytest_real_db",
        [
            sys.executable, "-m", "pytest", "--real-db", "-q",
            "--cov=researchos", "--cov-report=json:.health/coverage.json",
        ],
    )

    external_env = {**os.environ, "QROS_VERIFY_DATABASE_URL": args.database_url}
    checks["verify_migrations"] = run_check(
        "verify_migrations", [sys.executable, "scripts/verify_migrations.py"], env=external_env
    )
    checks["authz_check"] = run_check(
        "check_authz_coverage", [sys.executable, "scripts/check_authz_coverage.py"]
    )
    checks["rls_check"] = rls_check(args.database_url)
    checks["tenant_isolation_check"] = run_check(
        "tenant_isolation",
        ["psql", args.database_url, "-v", "ON_ERROR_STOP=1", "-f", str(TENANT_TEST)],
    )
    checks["backup_verify"] = run_check(
        "backup_verify",
        [
            sys.executable, "scripts/backup_verify.py",
            "--source-url", args.backup_source_url,
            "--target-admin-url", args.backup_target_admin_url,
            "--object-root-before", str(args.object_root_before),
            "--object-root-after", str(args.object_root_after),
        ],
    )

    coverage = read_coverage()
    all_pass = all(item["status"] == "PASS" for item in checks.values()) and coverage["status"] == "PASS"
    evidence = {
        "schema_version": 3,
        "commit": actual,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tests_passed": all_pass,
        "health_status": "PASS" if all_pass else "FAIL",
        "coverage": coverage,
        "rls_check": checks["rls_check"],
        "authz_check": checks["authz_check"],
        "tenant_isolation_check": checks["tenant_isolation_check"],
        "checks": checks,
    }
    output = ROOT / f"health_evidence_{actual}.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    verify_evidence(output, actual)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    print(f"HEALTH_EVIDENCE={output.name}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
