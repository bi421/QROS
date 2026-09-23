#!/usr/bin/env python3
"""Run the exact-release production health gate and emit immutable evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEALTH_DIR = ROOT / ".health"
COVERAGE_JSON = HEALTH_DIR / "coverage.json"
BACKUP_WORKFLOW = ROOT / ".github" / "workflows" / "production-db-backup.yml"
BACKUP_RESULT = HEALTH_DIR / "backup_verify.json"

REQUIRED_CHECKS = (
    "ruff",
    "pytest",
    "red_team_tenant_isolation",
    "rls_tenant_isolation",
    "authz_matrix",
    "backup_verify_contract",
)


def command_result(label: str, command: list[str], *, cwd: Path = ROOT) -> dict[str, object]:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "label": label,
        "command": command,
        "returncode": completed.returncode,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "stdout": completed.stdout.strip()[-12000:],
        "stderr": completed.stderr.strip()[-12000:],
    }


def git_value(args: list[str]) -> str:
    completed = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    return completed.stdout.strip()


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", help="Expected exact commit SHA; defaults to GITHUB_SHA when set.")
    parser.add_argument(
        "--skip-rls",
        action="store_true",
        help="Only for non-release local checks; release workflow must not use this.",
    )
    args = parser.parse_args()
    os.chdir(ROOT)

    expected_commit = args.commit or os.environ.get("GITHUB_SHA")
    actual_commit = git_value(["rev-parse", "HEAD"])
    if expected_commit and actual_commit != expected_commit:
        print(f"EXACT COMMIT CHECK FAILED: expected {expected_commit}, got {actual_commit}", file=sys.stderr)
        return 1

    HEALTH_DIR.mkdir(parents=True, exist_ok=True)
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

    if args.skip_rls:
        checks["rls_tenant_isolation"] = {
            "label": "rls_tenant_isolation",
            "command": [],
            "returncode": None,
            "status": "SKIPPED",
            "stdout": "",
            "stderr": "--skip-rls",
        }
    elif shutil.which("supabase"):
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

    statuses = [checks[name]["status"] for name in REQUIRED_CHECKS]
    overall = "PASS" if all(status == "PASS" for status in statuses) else "FAIL"

    evidence = {
        "schema_version": 2,
        "health_status": overall,
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "commit": actual_commit,
        "branch": git_value(["branch", "--show-current"]),
        "checks": checks,
        "test_results": {
            name: checks[name]["status"] for name in ("pytest", "red_team_tenant_isolation")
        },
        "coverage": coverage,
        "rls_check": checks["rls_tenant_isolation"],
        "authz_matrix_check": checks["authz_matrix"],
        "backup_verify": checks["backup_verify_contract"],
    }

    evidence_path = ROOT / f"health_evidence_{actual_commit}.json"
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(evidence, indent=2, sort_keys=True))
    print(f"HEALTH: {overall}")
    print(f"EVIDENCE: {evidence_path.name}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
