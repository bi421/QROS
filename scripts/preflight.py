#!/usr/bin/env python3
"""Fast local gate for push-time feedback.

Runs only checks justified by the current git diff:
- ruff on changed Python files
- BOM/UTF-8 checks on changed text files
- affected pytest tests selected from changed paths
- skips C++ configure/build unless C++ sources/build files changed

This is intentionally not a replacement for CI. CI remains the authoritative
full compatibility, native-build, and integration gate.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP_PREFIXES = ("cpp_quant_engine/",)
CPP_SUFFIXES = (".cpp", ".cc", ".cxx", ".h", ".hpp", ".cmake")
TEXT_SUFFIXES = {
    ".py", ".pyi", ".toml", ".yaml", ".yml", ".json", ".md", ".txt",
    ".ini", ".cfg", ".cmake", ".cpp", ".cc", ".cxx", ".h", ".hpp",
}


def run(cmd: list[str], label: str) -> int:
    print(f"\n=== {label} ===")
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT).returncode


def changed_files(base: str) -> list[str]:
    cmd = ["git", "diff", "--name-only", "--diff-filter=ACMR", base, "--"]
    out = subprocess.check_output(cmd, cwd=ROOT, text=True, encoding="utf-8-sig")
    return [line.replace("\\", "/") for line in out.splitlines() if line.strip()]


def affected_tests(files: list[str]) -> list[str]:
    tests: set[str] = set()
    for item in files:
        p = Path(item)
        if "/tests/" in item and p.name.startswith("test_"):
            tests.add(item)
            continue
        if item.startswith("researchos/"):
            parts = p.parts
            if len(parts) >= 2:
                package = Path(*parts[:-1])
                candidate = package / "tests"
                if candidate.exists():
                    tests.add(str(candidate).replace("\\", "/"))
                candidate = Path("researchos/tests")
                if candidate.exists():
                    tests.add(str(candidate).replace("\\", "/"))
        if item.startswith("scripts/"):
            candidate = Path("researchos/tests")
            if candidate.exists():
                tests.add(str(candidate).replace("\\", "/"))
    return sorted(tests)


def check_text(files: list[str]) -> int:
    failures = []
    for item in files:
        p = ROOT / item
        if p.suffix.lower() not in TEXT_SUFFIXES or not p.is_file():
            continue
        data = p.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            failures.append(f"BOM: {item}")
            continue
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            failures.append(f"UTF-8: {item}: {exc}")
    if failures:
        print("\n".join(failures))
        return 1
    print("TEXT INTEGRITY: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="HEAD~1", help="git diff base (default: HEAD~1)")
    parser.add_argument("--all", action="store_true", help="run the full Python pytest suite")
    args = parser.parse_args()

    files = changed_files(args.base)
    print("PREFLIGHT BASE:", args.base)
    print("CHANGED FILES:", len(files))
    for item in files:
        print(" -", item)
    if not files:
        print("PREFLIGHT: nothing to check")
        return 0

    status = 0
    py_files = [f for f in files if f.endswith((".py", ".pyi"))]
    if py_files:
        status |= run([sys.executable, "-m", "ruff", "check", *py_files], "RUFF (changed Python)")

    status |= check_text(files)

    tests = affected_tests(files)
    if args.all:
        tests = []
        status |= run([sys.executable, "-m", "pytest", "-q"], "PYTEST (full)")
    elif tests:
        status |= run([sys.executable, "-m", "pytest", "-q", *tests], "PYTEST (affected)")
    else:
        print("PYTEST: no affected test tree selected")

    cpp_changed = any(
        f.startswith(CPP_PREFIXES) and (
            f.endswith(CPP_SUFFIXES) or Path(f).name in {"CMakeLists.txt", "pyproject.toml"}
        )
        for f in files
    )
    if cpp_changed:
        print("C++: CHANGED — authoritative configure/build remains in CI; local preflight does not duplicate it.")
    else:
        print("C++: SKIPPED — no C++/native build input changed")

    print("\nPREFLIGHT:", "PASS" if status == 0 else "FAIL")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
