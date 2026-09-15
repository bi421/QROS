#!/usr/bin/env python3
"""Reject UTF-8 BOM and trailing whitespace in files presented by pre-commit/CI."""
from __future__ import annotations

import sys
from pathlib import Path

BOM = b"\xef\xbb\xbf"
TEXT_SUFFIXES = {".py", ".toml", ".yml", ".yaml", ".md", ".txt", ".json", ".ini", ".cfg", ".sh", ".ps1"}


def check(path: Path) -> list[str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [f"{path}: cannot read: {exc}"]
    failures: list[str] = []
    if raw.startswith(BOM):
        failures.append(f"{path}: UTF-8 BOM detected")
    if path.suffix.lower() in TEXT_SUFFIXES:
        text = raw.decode("utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            if line.rstrip("\r\n").endswith((" ", "\t")):
                failures.append(f"{path}:{number}: trailing whitespace")
    return failures


def main() -> int:
    paths = [Path(arg) for arg in sys.argv[1:]]
    if not paths:
        paths = [p for p in Path(".").rglob("*") if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES]
    failures = [failure for path in paths if path.exists() for failure in check(path)]
    if failures:
        print("TEXT INTEGRITY: FAIL")
        print("\n".join(f" - {failure}" for failure in failures))
        return 1
    print(f"TEXT INTEGRITY: PASS ({len(paths)} files checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
