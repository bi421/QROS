#!/usr/bin/env python3
"""Run the canonical local health gate in one command.

The command intentionally reports facts, not interpretations:
ruff -> pytest -> C++ configure/build -> git status.
Any failed command makes the overall health check fail.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP_SOURCE = ROOT / "cpp_quant_engine"
HEALTH_BUILD = ROOT / ".healthcheck" / "cpp"


def run(label: str, command: list[str], *, cwd: Path = ROOT) -> bool:
    print(f"\n=== {label} ===")
    print("$ " + " ".join(command))
    completed = subprocess.run(command, cwd=cwd, check=False)
    print(f"[{label}] {'PASS' if completed.returncode == 0 else 'FAIL'}")
    return completed.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-cpp", action="store_true", help="Skip C++ configure/build locally")
    args = parser.parse_args()

    os.chdir(ROOT)
    results: list[tuple[str, bool]] = []

    if shutil.which("ruff"):
        results.append(("RUFF", run("RUFF", ["ruff", "check", "."])))
    else:
        results.append(("RUFF", run("RUFF", [sys.executable, "-m", "ruff", "check", "."])))

    results.append(("PYTEST", run("PYTEST", [sys.executable, "-m", "pytest", "-q"])))

    if args.skip_cpp:
        print("\n=== C++ COMPILE ===\n[ C++ COMPILE ] SKIPPED (--skip-cpp)")
        results.append(("C++ COMPILE", True))
    elif not CPP_SOURCE.exists():
        print("\n=== C++ COMPILE ===\n[ C++ COMPILE ] FAIL: cpp_quant_engine/ not found")
        results.append(("C++ COMPILE", False))
    elif not shutil.which("cmake"):
        print("\n=== C++ COMPILE ===\n[ C++ COMPILE ] FAIL: cmake not found")
        results.append(("C++ COMPILE", False))
    else:
        HEALTH_BUILD.mkdir(parents=True, exist_ok=True)
        configured = run(
            "C++ CONFIGURE",
            ["cmake", "-S", str(CPP_SOURCE), "-B", str(HEALTH_BUILD), "-DCMAKE_BUILD_TYPE=Release"],
        )
        built = configured and run("C++ BUILD", ["cmake", "--build", str(HEALTH_BUILD), "--config", "Release"])
        results.append(("C++ COMPILE", built))

    print("\n=== GIT STATUS ===")
    git_ok = run("GIT STATUS", ["git", "status", "--short", "--branch"])
    results.append(("GIT STATUS", git_ok))

    print("\n=== FINAL HEALTH ===")
    for name, passed in results:
        print(f"{'PASS' if passed else 'FAIL':5} {name}")
    failed = [name for name, passed in results if not passed]
    if failed:
        print("FAILURES: " + ", ".join(failed))
        return 1
    print("HEALTH: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
