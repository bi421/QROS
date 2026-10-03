#!/usr/bin/env python3
"""Run the exact-release health gates and emit immutable SHA-scoped evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
TENANT_TEST = ROOT / "supabase" / "tests" / "tenant_isolation_test.sql"
REQUIRED_RLS_TABLES = (
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


def run_check(label: str, command: list[str], *, cwd: Path = ROOT) -> dict[str, object]:
    completed = subprocess.run(
        command, cwd=cwd, text=True, capture_output=True, check=False
    )
    return {
        "label": label,
        "command": command,
        "returncode": completed.returncode,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
    }


def db_url_for_database(admin_url: str, database: str) -> str:
    parts = urlsplit(admin_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.pop("dbname", None)
    return urlunsplit(
        (parts.scheme, parts.netloc, f"/{database}", urlencode(query), parts.fragment)
    )


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
    result = run_check(
        "rls_check",
        ["psql", database_url, "-Atqc", sql],
    )
    missing = result["stdout"].strip()
    if result["status"] == "PASS" and missing:
        result["status"] = "FAIL"
        result["returncode"] = 1
        result["stderr"] = f"RLS disabled on required tables: {missing}"
    return result


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
    if actual != args.expected_commit:
        raise SystemExit(
            f"exact-release violation: expected {args.expected_commit}, got {actual}"
        )

    checks: dict[str, dict[str, object]] = {}

    checks["ruff"] = run_check(
        "ruff", [sys.executable, "-m", "ruff", "check", "."]
    )

    coverage_json = ROOT / ".health" / "coverage.json"
    coverage_json.parent.mkdir(parents=True, exist_ok=True)
    pytest_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--cov=researchos",
        "--cov-report=json:.health/coverage.json",
    ]
    checks["full_test_suite"] = run_check("full_test_suite", pytest_cmd)

    coverage: dict[str, object]
    if coverage_json.exists():
        try:
            raw = json.loads(coverage_json.read_text(encoding="utf-8"))
            totals = raw.get("totals", {})
            coverage = {
                "percent_covered": totals.get("percent_covered"),
                "covered_lines": totals.get("covered_lines"),
                "num_statements": totals.get("num_statements"),
                "source": ".health/coverage.json",
            }
        except (OSError, json.JSONDecodeError, AttributeError):
            coverage = {"status": "FAIL", "source": ".health/coverage.json"}
        else:
            if not isinstance(coverage["percent_covered"], (int, float)):
                coverage["status"] = "FAIL"
            else:
                coverage["status"] = "PASS"
    else:
        coverage = {"status": "FAIL", "source": ".health/coverage.json"}

    checks["observability"] = run_check(
        "observability",
        [sys.executable, "-m", "pytest", "researchos/saas/tests/test_observability.py", "researchos/saas/tests/test_worker.py", "-q"],
    )

    checks["authz_matrix"] = run_check(
        "authz_matrix", [sys.executable, "scripts/verify_authz_routes.py"]
    )
    checks["rls"] = rls_check(args.database_url)

    # This SQL suite is the repository's adversarial/red-team tenant boundary.
    checks["tenant_isolation_red_team"] = run_check(
        "tenant_isolation_red_team",
        ["psql", args.database_url, "-v", "ON_ERROR_STOP=1", "-f", str(TENANT_TEST)],
    )

    checks["backup_restore"] = run_check(
        "backup_restore",
        [
            sys.executable,
            "scripts/backup_verify.py",
            "--source-url",
            args.backup_source_url,
            "--target-admin-url",
            args.backup_target_admin_url,
            "--object-root-before",
            str(args.object_root_before),
            "--object-root-after",
            str(args.object_root_after),
        ],
    )

    evidence = {
        "schema_version": 2,
        "commit": actual,
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "health_status": (
            "PASS"
            if all(check["status"] == "PASS" for check in checks.values())
            else "FAIL"
        ),
        "test_results": {
            name: {
                "status": result["status"],
                "returncode": result["returncode"],
            }
            for name, result in checks.items()
        },
        "coverage": coverage,
        "rls_check": checks["rls"],
        "authz_matrix_check": checks["authz_matrix"],
        "checks": checks,
    }

    output = ROOT / f"health_evidence_{actual}.json"
    output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
    print(f"HEALTH_EVIDENCE={output.name}")
    return 0 if evidence["health_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
