#!/usr/bin/env python3
"""Validate a QROS engineering task contract before autonomous work."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

REQUIRED_SECTIONS = (
    "## Task",
    "## Scope",
    "## Preconditions",
    "## Acceptance criteria",
    "## Validation",
    "## Risk",
    "## Autonomy limits",
    "## Completion evidence",
)

PLACEHOLDER_RE = re.compile(r"(?m)^-\s*(?:ID|Goal|Why|Current branch/ref|Maximum repair attempts):\s*$")


def validate_contract(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.is_file():
        return [f"task contract not found: {path}"]

    text = path.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        if not re.search(rf"(?m)^{re.escape(section)}\s*$", text):
            errors.append(f"missing required section: {section}")

    for match in PLACEHOLDER_RE.finditer(text):
        errors.append(f"unfilled required field: {match.group(0).strip()}")

    allowed = _section_body(text, "### Allowed", "### Forbidden")
    forbidden = _section_body(text, "### Forbidden", "## Preconditions")
    if not _has_nonempty_bullet(allowed):
        errors.append("scope allowed list must contain at least one non-empty item")
    if not _has_nonempty_bullet(forbidden):
        errors.append("scope forbidden list must contain at least one non-empty item")

    acceptance = _section_body(text, "## Acceptance criteria", "## Validation")
    if not re.search(r"(?m)^- \[[ xX]\] .+\S", acceptance):
        errors.append("acceptance criteria must contain at least one non-empty checklist item")

    return errors


def _section_body(text: str, start: str, end: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        return ""
    start_index += len(start)
    end_index = text.find(end, start_index)
    return text[start_index:] if end_index < 0 else text[start_index:end_index]


def _has_nonempty_bullet(text: str) -> bool:
    return bool(re.search(r"(?m)^-\s+\S", text))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    args = parser.parse_args()

    errors = validate_contract(args.contract)
    if errors:
        print("TASK CONTRACT: FAIL")
        for error in errors:
            print(" -", error)
        return 1

    print("TASK CONTRACT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
