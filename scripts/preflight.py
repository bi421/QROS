#!/usr/bin/env python3
"""Dependency-aware local test router.

Profiles:
- fast: changed tests plus mapped fast test trees; frozen suites are skipped
- frozen: fast profile plus every frozen validation group
- full: the complete pytest suite

Ruff and text-integrity checks intentionally live in pre-commit. CI remains
authoritative for compatibility, native builds, integration, and full coverage.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Expensive tests are evidence, not default developer feedback.  A group is
# invalidated whenever any declared dependency path changes.
FROZEN_GROUPS: dict[str, dict[str, tuple[str, ...]]] = {
    "phase52-comparison": {
        "dependencies": (
            "researchos/experiments/phase52/",
            "researchos/experiments/phase52_rebuild/",
        ),
        "tests": (
            "researchos/experiments/phase52/tests/test_phase52_feature_sets.py::test_phase52_comparison_returns_all_isolated_feature_sets",
            "researchos/experiments/phase52/tests/test_phase52_feature_sets.py::test_phase52_comparison_is_deterministic",
            "researchos/experiments/phase52/tests/test_phase52_feature_sets_v2.py::test_comparison_has_identical_fold_geometry_and_explicit_feature_sets",
            "researchos/experiments/phase52/tests/test_phase52_feature_sets_v2.py::test_comparison_is_reproducible",
        ),
    },
    "institutional-audit-performance": {
        "dependencies": (
            "researchos/storage/",
            "researchos/objects/",
            "researchos/core/",
        ),
        "tests": (
            "researchos/tests/test_institutional.py::TestLongAuditChain::test_10k_chain_verify_speed",
        ),
    },
}

CPP_PREFIX = "cpp_quant_engine/"
CPP_SUFFIXES = (".cpp", ".cc", ".cxx", ".h", ".hpp", ".cmake")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def diff_base() -> str:
    for candidate in ("origin/main", "main"):
        try:
            return git("merge-base", "HEAD", candidate)
        except subprocess.CalledProcessError:
            continue
    return "HEAD~1"


def names(*args: str) -> set[str]:
    try:
        out = git("diff", "--name-only", "--diff-filter=ACMR", *args)
    except subprocess.CalledProcessError:
        return set()
    return {line.replace("\\", "/") for line in out.splitlines() if line.strip()}


def changed_files(base: str) -> list[str]:
    files = names(base, "HEAD") | names() | names("--cached")
    try:
        untracked = git("ls-files", "--others", "--exclude-standard")
        files |= {line.replace("\\", "/") for line in untracked.splitlines() if line.strip()}
    except subprocess.CalledProcessError:
        pass
    return sorted(files)


def overlaps(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in prefixes)


def frozen_invalidated(files: list[str], group: dict[str, tuple[str, ...]]) -> bool:
    return any(overlaps(item, group["dependencies"]) for item in files)


def direct_tests(files: list[str]) -> list[str]:
    selected: set[str] = set()
    for item in files:
        path = Path(item)
        if "/tests/" in item and path.name.startswith("test_"):
            selected.add(item)
            continue
        if item.startswith("researchos/") and "/tests/" not in item:
            parts = path.parts
            if len(parts) >= 3:
                sibling = Path(*parts[:-1]) / "tests"
                if (ROOT / sibling).is_dir():
                    selected.add(sibling.as_posix())
    return sorted(selected)


def run(label: str, *cmd: str) -> int:
    print(f"\n=== {label} ===")
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("fast", "frozen", "full"), default="fast")
    parser.add_argument("--base", help="override git diff base")
    parser.add_argument("--frozen", action="store_true", help="alias for --profile frozen")
    parser.add_argument("--full", action="store_true", help="alias for --profile full")
    args = parser.parse_args()
    profile = "full" if args.full else "frozen" if args.frozen else args.profile

    base = args.base or diff_base()
    files = changed_files(base)
    print("PREFLIGHT PROFILE:", profile)
    print("PREFLIGHT BASE:", base)
    print("CHANGED FILES:", len(files))
    for item in files:
        print(" -", item)

    if not files and profile != "full":
        print("PREFLIGHT: no changed files")
        return 0

    if profile == "full":
        return run("PYTEST (full)", sys.executable, "-m", "pytest", "-q")

    selected = direct_tests(files)
    for name, group in FROZEN_GROUPS.items():
        invalidated = frozen_invalidated(files, group)
        if profile == "frozen" or invalidated:
            selected.extend(group["tests"])
            state = "RUN — dependency changed" if invalidated else "RUN — explicitly requested"
        else:
            state = "FROZEN — dependencies unchanged"
        print(f"{name}: {state}")

    selected = sorted(set(selected))
    status = 0
    if selected:
        status |= run("PYTEST (affected/frozen)", sys.executable, "-m", "pytest", "-q", *selected)
    else:
        print("PYTEST: no affected tests selected")

    native_changed = any(
        item.startswith(CPP_PREFIX) and (item.endswith(CPP_SUFFIXES) or Path(item).name in {"CMakeLists.txt", "pyproject.toml"})
        for item in files
    )
    if native_changed:
        print("C++: CHANGED — CI is authoritative; local native build is intentionally skipped")
    else:
        print("C++: SKIPPED — no native input changed")

    print("\nPREFLIGHT:", "PASS" if status == 0 else "FAIL")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
