#!/usr/bin/env python3
"""Reject source/config encoding hazards before they reach CI or runtime."""
from __future__ import annotations

import sys
from pathlib import Path

BOM = b"\xef\xbb\xbf"

# These files are parsed/executed by CI, Python, YAML tooling, or shells.
VALIDATED_SUFFIXES = {
    ".py", ".toml", ".yml", ".yaml", ".json", ".ini", ".cfg", ".sh", ".ps1",
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".cmake",
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
        if path.is_file() and not any(part in SKIP_DIRS for part in path.parts):
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

    # BOM is a repository-level hazard even when the file is not parsed as UTF-8
    # by this checker, so detect it directly from the raw bytes.
    if raw.startswith(BOM):
        failures.append(f"{path}: UTF-8 BOM detected")

    if path.suffix.lower() not in VALIDATED_SUFFIXES:
        return failures

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        failures.append(f"{path}: invalid UTF-8: {exc}")
        return failures

    if "\ufeff" in text:
        failures.append(f"{path}: UTF-8 BOM character detected in text")
    if "\x00" in text:
        failures.append(f"{path}: NUL character detected in text")

    return failures


def main() -> int:
    paths = [Path(arg) for arg in sys.argv[1:]] or iter_files()
    failures = [failure for path in paths if path.exists() for failure in check(path)]
    if failures:
        print("TEXT INTEGRITY: FAIL")
        print("\n".join(f" - {failure}" for failure in failures))
        return 1

    print(f"TEXT INTEGRITY: PASS ({len(paths)} files checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
