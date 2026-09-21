#!/usr/bin/env python3
"""Classify CI failure logs conservatively and deterministically."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass

CATEGORIES = (
    "implementation defect",
    "test/contract mismatch",
    "formatting/static failure",
    "environment/tooling failure",
    "CI orchestration failure",
    "missing prerequisite",
    "ambiguous/unsafe",
)

@dataclass(frozen=True)
class Classification:
    category: str
    confidence: str
    repairable: bool
    evidence: tuple[str, ...]


def classify(log: str) -> Classification:
    if not log.strip():
        return Classification("ambiguous/unsafe", "none", False, ("empty CI log",))

    text = log.lower()
    evidence: list[str] = []

    orchestration = _matches(
        text,
        (
            r"no jobs",
            r"jobs:s*[]",
            r"total_count:s*0",
            r"workflow.*(?:cancelled|canceled)",
            r"strategy configuration was canceled",
            r"no steps were run",
        ),
    )
    tooling = _matches(
        text,
        (
            r"command not found",
            r"could not resolve host",
            r"network is unreachable",
            r"temporary failure in name resolution",
            r"pip .*(?:install|download).*(?:failed|error)",
            r"docker daemon.*(?:not running|unavailable)",
        ),
    )
    prerequisite = _matches(
        text,
        (
            r"required secret.*(?:missing|not set)",
            r"secret .* not found",
            r"file .* not found",
            r"no such file or directory",
            r"missing prerequisite",
            r"module named .* not found",
        ),
    )
    static = _matches(
        text,
        (
            r"ruff (?:check|format).*failed",
            r"pre-commit.*failed",
            r"syntaxerror:",
            r"trailing whitespace",
            r"no newline at end of file",
            r"[efw]d{3}",
        ),
    )
    contract = _matches(
        text,
        (
            r"assert .*expected",
            r"assert .*==",
            r"assertionerror",
            r"test_.*failed",
            r"contract.*(?:mismatch|violation|failed)",
            r"expected .* but got",
        ),
    )
    implementation = _matches(
        text,
        (
            r"traceback (most recent call last)",
            r"raise (?:valueerror|typeerror|keyerror|attributeerror)",
            r"failed in .*.py:d+",
            r"error in .*.py:d+",
        ),
    )

    if orchestration:
        evidence.extend(orchestration)
        if tooling or prerequisite or static or contract or implementation:
            return Classification(
                "ambiguous/unsafe",
                "low",
                False,
                tuple(evidence + tooling + prerequisite + static + contract + implementation),
            )
        return Classification("CI orchestration failure", "high", False, tuple(evidence))

    if len([bool(tooling), bool(prerequisite), bool(static), bool(contract), bool(implementation)]) > 1:
        groups = [tooling, prerequisite, static, contract, implementation]
        evidence.extend(item for group in groups for item in group)
        return Classification("ambiguous/unsafe", "low", False, tuple(evidence))

    if tooling:
        return Classification("environment/tooling failure", "high", True, tuple(tooling))
    if prerequisite:
        return Classification("missing prerequisite", "high", True, tuple(prerequisite))
    if static:
        return Classification("formatting/static failure", "high", True, tuple(static))
    if contract:
        return Classification("test/contract mismatch", "medium", True, tuple(contract))
    if implementation:
        return Classification("implementation defect", "medium", True, tuple(implementation))

    return Classification("ambiguous/unsafe", "none", False, ("no supported failure signature",))


def _matches(text: str, patterns: tuple[str, ...]) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", nargs="?", help="CI log file; stdin is used when omitted")
    args = parser.parse_args()

    log = open(args.log, encoding="utf-8").read() if args.log else sys.stdin.read()
    result = classify(log)
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
