#!/usr/bin/env python3
"""Reject malformed or unsafe text files before they reach CI/runtime."""
from __future__ import annotations

import sys
from pathlib import Path

BOM = b"\xef\xbb\xbf"
TEXT_SUFFIXES = {
    ".py", ".toml", ".yml", ".yaml", ".md", ".txt", ".json",
    ".ini", ".cfg", ".sh", ".ps1",
}
SKIP_DIRS = {
    ".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    ".tox", ".venv", "venv", "build", "dist",
}
FORBIDDEN_PATH_MARKERS = (
    ".nanobind_migration_backup",
    ".tmp-pr67",
)


def iter_files() -> list[Path]:
    result: list[Path] = []
    for path in Path(".").rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        result.append(path)
    return result


def check(path: Path) -> list[str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [f"{path}: cannot read: {exc}"]

    failures: list[str] = []
    normalized = path.as_posix()
    if any(marker in normalized for marker in FORBIDDEN_PATH_MARKERS):
        failures.append(f"{path}: forbidden temporary artifact path")

    if raw.startswith(BOM):
        failures.append(f"{path}: UTF-8 BOM detected")

    if path.suffix.lower() in TEXT_SUFFIXES:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            failures.append(f"{path}: invalid UTF-8: {exc}")
            return failures

        if "\ufeff" in text:
            failures.append(f"{path}: UTF-8 BOM character detected in text")

        if "\x00" in text:
            failures.append(f"{path}: NUL character detected in text")

        for number, line in enumerate(text.splitlines(), 1):
            if line.rstrip("\r\n").endswith((" ", "\t")):
                failures.append(f"{path}:{number}: trailing whitespace")

    return failures


def main() -> int:
    paths = [Path(arg) for arg in sys.argv[1:]]
    if not paths:
        paths = iter_files()

    failures = [failure for path in paths if path.exists() for failure in check(path)]
    if failures:
        print("TEXT INTEGRITY: FAIL")
        print("\n".join(f" - {failure}" for failure in failures))
        return 1

    print(f"TEXT INTEGRITY: PASS ({len(paths)} files checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
