#!/usr/bin/env python3
"""Run the exact-release production health gate and emit immutable evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import shutil
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
HEALTH_DIR = ROOT / ".health"
COVERAGE_JSON = HEALTH_DIR / "coverage.json"
BACKUP_WORKFLOW = ROOT / ".github" / "workflows" / "production-db-backup.yml"
BACKUP_RESULT = HEALTH_DIR / "backup_verify.json"
HEALTH_JSON = HEALTH_DIR / "health_evidence.json"
evidence_path = HEALTH_JSON
REQUIRED_RLS_TABLES = ("research_runs", "research_claims", "research_evidence", "research_findings")

REQUIRED_CHECKS = (
    "ruff",
    "pytest",
    "red_team_tenant_isolation",
    "real_tenant_isolation",
    "rls_tenant_isolation",
    "authz_matrix",
    "backup_verify_contract",
)


def command_result(label: str, command: list[str], *, cwd: Path = ROOT) -> dict[str, object]:
    resolved = shutil.which(command[0]) or command[0]
    try:
        completed = subprocess.run(
            [resolved, *command[1:]],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return {
            "label": label,
            "command": command,
            "returncode": 1,
            "status": "FAIL",
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }
    return {
        "label": label,
        "command": command,
        "returncode": completed.returncode,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "stdout": completed.stdout.strip()[-12000:],
        "stderr": completed.stderr.strip()[-12000:],
    }


def run_check(label: str, command: list[str]) -> dict[str, object]:
    return command_result(label, command)


def git_value(args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"git command failed: {' '.join(args)}")
    return result.stdout.strip()


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


def backup_verify_contract() -> dict[str, object]:
    if not BACKUP_WORKFLOW.exists():
        return {
            "label": "backup_verify_contract",
            "status": "FAIL",
            "returncode": 1,
            "command": [],
            "stdout": "",
            "stderr": f"missing {BACKUP_WORKFLOW.relative_to(ROOT)}",
        }
    text = BACKUP_WORKFLOW.read_text(encoding="utf-8")
    required = (
        "sha256sum --check",
        "aws s3api head-object",
    )
    missing = [item for item in required if item not in text]
    return {
        "label": "backup_verify_contract",
        "status": "PASS" if not missing else "FAIL",
        "returncode": 0 if not missing else 1,
        "command": ["repository backup workflow contract"],
        "stdout": "required local checksum and remote object verification present",
        "stderr": "" if not missing else f"missing: {', '.join(missing)}",
        "required": list(required),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-cpp", action="store_true", help="Skip C++ configure/build")
    parser.add_argument("--exact-commit", help="Require HEAD to equal this commit SHA")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    actual = git_sha()
    if args.exact_commit and actual != args.exact_commit:
        print(
            f"EXACT COMMIT MISMATCH: expected {args.exact_commit}, got {actual}",
            file=sys.stderr,
        )
        return 2

    checks: dict[str, dict[str, object]] = {}

    ruff = ["ruff", "check", "."] if shutil.which("ruff") else [sys.executable, "-m", "ruff", "check", "."]
    checks["ruff"] = command_result("ruff", ruff)

    pytest_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--cov=researchos",
        "--cov-report=json:.health/coverage.json",
    ]
    checks["pytest"] = command_result("pytest", pytest_cmd)

    checks["red_team_tenant_isolation"] = command_result(
        "red_team_tenant_isolation",
        [
            sys.executable,
            "-m",
            "pytest",
            "researchos/saas/tests/test_api.py",
            "-q",
            "-k",
            "cross_tenant or workspace_header",
        ],
    )
    checks["real_tenant_isolation"] = command_result(
        "real_tenant_isolation",
        [
            sys.executable,
            "-m",
            "pytest",
            "researchos/saas/tests/test_tenant_isolation_real.py",
            "--real-db",
            "-v",
        ],
    )

    if shutil.which("supabase"):
        checks["rls_tenant_isolation"] = command_result(
            "rls_tenant_isolation",
            ["supabase", "test", "db", "supabase/tests/tenant_isolation_test.sql"],
        )
    else:
        checks["rls_tenant_isolation"] = {
            "label": "rls_tenant_isolation",
            "command": ["supabase", "test", "db", "supabase/tests/tenant_isolation_test.sql"],
            "returncode": 1,
            "status": "FAIL",
            "stdout": "",
            "stderr": "supabase CLI is required for the release RLS gate",
        }

    checks["authz_matrix"] = command_result(
        "authz_matrix",
        [
            sys.executable,
            "-m",
            "pytest",
            "researchos/saas/tests/test_authz_matrix.py",
            "-q",
        ],
    )
    if BACKUP_RESULT.exists():
        try:
            checks["backup_verify_contract"] = json.loads(BACKUP_RESULT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            checks["backup_verify_contract"] = {
                "label": "backup_verify_contract",
                "status": "FAIL",
                "returncode": 1,
                "command": [],
                "stdout": "",
                "stderr": f"invalid backup verification evidence: {exc}",
            }
    else:
        checks["backup_verify_contract"] = backup_verify_contract()

    coverage: dict[str, object] = {"status": "UNAVAILABLE"}
    if COVERAGE_JSON.exists():
        try:
            payload = json.loads(COVERAGE_JSON.read_text(encoding="utf-8"))
            totals = payload.get("totals", {})
            coverage = {
                "status": "PASS",
                "percent_covered": totals.get("percent_covered"),
                "covered_lines": totals.get("covered_lines"),
                "num_statements": totals.get("num_statements"),
                "missing_lines": totals.get("missing_lines"),
            }
        except (OSError, json.JSONDecodeError) as exc:
            coverage = {"status": "FAIL", "error": str(exc)}
    if checks["pytest"]["status"] != "PASS" or coverage["status"] != "PASS":
        coverage["status"] = "FAIL"

    # SKIPPED is an intentional non-blocking state (for example --skip-cpp).
    # Only an explicit FAIL makes the overall health gate fail.
    failures = [check["label"] for check in checks.values() if check["status"] == "FAIL"]
    overall = "FAIL" if failures else "PASS"
    evidence = {
        "schema_version": 2,
        "health_status": overall,
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "commit": actual,
        "branch": git_value(["branch", "--show-current"]),
        "checks": checks,
        "test_results": {
            name: checks[name]["status"] for name in ("pytest", "red_team_tenant_isolation", "real_tenant_isolation")
        },
        "coverage": coverage,
        "rls_check": checks["rls_tenant_isolation"],
        "authz_matrix_check": checks["authz_matrix"],
        "backup_verify": checks["backup_verify_contract"],
    }

    HEALTH_DIR.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    HEALTH_JSON.write_text(serialized, encoding="utf-8")
    exact_evidence = HEALTH_DIR / f"health_evidence_{evidence['commit']}.json"
    exact_evidence.write_text(serialized, encoding="utf-8")

    print(json.dumps(evidence, indent=2, sort_keys=True))
    print(f"HEALTH: {overall}")
    print(f"EVIDENCE: {evidence_path.name}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
