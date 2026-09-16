#!/usr/bin/env python3
"""Static QROS governance gate.

This gate enforces architecture boundaries that can be checked without executing
research code. It complements, rather than replaces, tests and health checks.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_DOCS = (
    "docs/governance/RESEARCHOS_QUANT_RESEARCH_OS_GOVERNANCE.md",
    "docs/governance/RESEARCHOS_DEFINITION_OF_DONE.md",
    "docs/architecture/QUANT_RESEARCH_OS_REFERENCE_ARCHITECTURE_2026.md",
    "docs/architecture/RESEARCHOS_TECHNOLOGY_ECOSYSTEM_2026.md",
    "docs/product/RESEARCHOS_ANALYSIS_EXECUTION_CONTRACT_2026.md",
    "docs/product/RESEARCHOS_PROBABILITY_AND_EDGE_FRAMEWORK_2026.md",
)

# Research Core must not acquire live execution dependencies implicitly.
FORBIDDEN_EXECUTION_IMPORTS = (
    "ccxt",
    "ib_insync",
    "MetaTrader5",
    "alpaca_trade_api",
    "oandapyV20",
    "quickfix",
)


def changed_paths(base: str | None) -> list[str]:
    command = ["git", "diff", "--name-only", "--diff-filter=ACMR"]
    command.append(f"{base}...HEAD" if base else "HEAD")
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
    return [p.strip().replace("\\", "/") for p in completed.stdout.splitlines() if p.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=None)
    args = parser.parse_args()

    failures: list[str] = []

    for relative in REQUIRED_DOCS:
        if not (ROOT / relative).is_file():
            failures.append(f"missing mandatory governance document: {relative}")

    try:
        paths = changed_paths(args.base)
    except subprocess.CalledProcessError as exc:
        print(f"QROS GOVERNANCE: FAIL: git diff failed: {exc.stderr.strip()}")
        return 1

    for relative in paths:
        if not relative.startswith("researchos/") or not relative.endswith(".py"):
            continue
        text = (ROOT / relative).read_text(encoding="utf-8")
        for package in FORBIDDEN_EXECUTION_IMPORTS:
            pattern = rf"(^|\n)\s*(?:from\s+{re.escape(package)}|import\s+{re.escape(package)})(?:\s|\.|$)"
            if re.search(pattern, text):
                failures.append(
                    f"research-core execution boundary violation: {relative} imports {package}"
                )

    if failures:
        print("QROS GOVERNANCE: FAIL")
        for failure in failures:
            print(" - " + failure)
        return 1

    print(f"QROS GOVERNANCE: PASS ({len(paths)} changed paths checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
