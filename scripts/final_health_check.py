#!/usr/bin/env python3
"""Run the canonical local health gate and emit machine-readable evidence."""
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
CPP_SOURCE = ROOT / "researchos" / "engines" / "quant"
HEALTH_BUILD = ROOT / ".healthcheck" / "cpp"
HEALTH_DIR = ROOT / ".health"
HEALTH_JSON = HEALTH_DIR / "last_run.json"


def command_result(label: str, command: list[str], *, cwd: Path = ROOT) -> dict[str, object]:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    return {
        "label": label,
        "command": command,
        "returncode": completed.returncode,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "stdout": stdout[-12000:],
        "stderr": stderr[-12000:],
    }


def git_value(args: list[str]) -> str:
    completed = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    return completed.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-cpp", action="store_true", help="Skip C++ configure/build")
    parser.add_argument("--logs-file", type=Path, default=None, help="Validate newline-delimited JSON observability logs")
    parser.add_argument("--request-id", default=None, help="Require this request_id in every validated log record")
    args = parser.parse_args()
    os.chdir(ROOT)

    checks: dict[str, dict[str, object]] = {}

    ruff = ["ruff", "check", "."] if shutil.which("ruff") else [sys.executable, "-m", "ruff", "check", "."]
    checks["ruff"] = command_result("ruff", ruff)
    checks["pytest"] = command_result("pytest", [sys.executable, "-m", "pytest", "-q"])

    if args.skip_cpp:
        checks["cpp_compile"] = {
            "label": "cpp_compile",
            "command": [],
            "returncode": None,
            "status": "SKIPPED",
            "stdout": "",
            "stderr": "--skip-cpp",
        }
    elif not CPP_SOURCE.exists() or not shutil.which("cmake"):
        checks["cpp_compile"] = {
            "label": "cpp_compile",
            "command": [],
            "returncode": 1,
            "status": "FAIL",
            "stdout": "",
            "stderr": "cpp_quant_engine/ or cmake is unavailable",
        }
    else:
        HEALTH_BUILD.mkdir(parents=True, exist_ok=True)
        configure = command_result(
            "cpp_configure",
            ["cmake", "-S", str(CPP_SOURCE), "-B", str(HEALTH_BUILD), "-DCMAKE_BUILD_TYPE=Release"],
        )
        if configure["status"] == "PASS":
            build = command_result("cpp_build", ["cmake", "--build", str(HEALTH_BUILD), "--config", "Release"])
        else:
            build = {"label": "cpp_build", "command": [], "returncode": 1, "status": "NOT_RUN", "stdout": "", "stderr": "configure failed"}
        checks["cpp_compile"] = {
            "label": "cpp_compile",
            "status": "PASS" if build["status"] == "PASS" else "FAIL",
            "configure": configure,
            "build": build,
        }

    if args.logs_file is not None:
        log_path = args.logs_file if args.logs_file.is_absolute() else ROOT / args.logs_file
        try:
            records = []
            for line_no, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError(f"line {line_no}: log record is not an object")
                for field in ("timestamp", "level", "request_id", "message"):
                    if field not in record:
                        raise ValueError(f"line {line_no}: missing {field}")
                if args.request_id is not None and record["request_id"] != args.request_id:
                    raise ValueError(f"line {line_no}: request_id mismatch")
                records.append(record)
            checks["logs_json"] = {"label": "logs_json", "status": "PASS", "record_count": len(records), "path": str(log_path)}
        except Exception as exc:
            checks["logs_json"] = {"label": "logs_json", "status": "FAIL", "record_count": 0, "path": str(log_path), "stderr": str(exc)}
    git_status = command_result("git_status", ["git", "status", "--short", "--branch"])
    checks["git_status"] = git_status

    statuses = [check["status"] for check in checks.values()]
    overall = "PASS" if all(status == "PASS" for status in statuses) else "FAIL"
    evidence = {
        "schema_version": 1,
        "health_status": overall,
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "commit": git_value(["rev-parse", "HEAD"]),
        "branch": git_value(["branch", "--show-current"]),
        "checks": checks,
    }

    HEALTH_DIR.mkdir(parents=True, exist_ok=True)
    HEALTH_JSON.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(evidence, indent=2, sort_keys=True))
    print(f"HEALTH: {overall}")
    print(f"EVIDENCE: {HEALTH_JSON.relative_to(ROOT)}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
