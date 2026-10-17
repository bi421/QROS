from __future__ import annotations

"""QROS hygiene audit. Safe by default: reports only; --clean-caches removes derived caches only."""
import argparse
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAFE_CACHE_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".hypothesis",
    ".tox",
    ".nox",
}
PROTECTED_NAMES = {
    ".git",
    ".venv",
    ".venv-mypy",
    "venv",
    "env",
    "data",
    "artifacts",
    ".health",
    ".healthcheck",
    "reports",
    "AUDIT_REPORT",
    "archive",
    "supabase",
    "migrations",
    "tests",
    "fixtures",
}


def run_git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=True)
    return result.stdout


def size_bytes(path: Path) -> int:
    total = 0
    try:
        for base, dirs, files in os.walk(path, onerror=lambda _e: None):
            dirs[:] = [d for d in dirs if d not in {".git", ".venv", ".venv-mypy", "venv"}]
            for name in files:
                try:
                    total += (Path(base) / name).stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def is_under_git(path: Path, tracked: set[str], untracked: set[str]) -> bool:
    rel = path.relative_to(ROOT).as_posix().rstrip("/")
    return any(x == rel or x.startswith(rel + "/") for x in tracked | untracked)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clean-caches",
        action="store_true",
        help="remove only untracked, derived cache directories",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable report")
    args = parser.parse_args()
    branch = run_git("branch", "--show-current").strip()
    head = run_git("rev-parse", "HEAD").strip()
    tracked = set(run_git("ls-files", "-z").split("\0"))
    untracked = {
        x.rstrip("/")
        for x in run_git("ls-files", "--others", "--exclude-standard", "-z").split("\0")
        if x
    }
    dirty = run_git("status", "--porcelain", "-z").split("\0")
    candidates: list[dict] = []
    for base, dirs, _files in os.walk(ROOT, topdown=True):
        here = Path(base)
        dirs[:] = [
            d for d in dirs if d not in PROTECTED_NAMES and d not in {"node_modules", ".git"}
        ]
        for name in list(dirs):
            if name not in SAFE_CACHE_NAMES:
                continue
            candidate = here / name
            try:
                rel = candidate.relative_to(ROOT).as_posix()
                if is_under_git(candidate, tracked, untracked):
                    continue
                amount = size_bytes(candidate)
                if amount:
                    candidates.append(
                        {
                            "path": rel,
                            "bytes": amount,
                            "kind": "derived-cache",
                            "safe_to_remove": True,
                        }
                    )
                dirs.remove(name)
            except (OSError, ValueError):
                continue
    candidates.sort(key=lambda x: x["bytes"], reverse=True)
    removed: list[dict] = []
    if args.clean_caches:
        for item in candidates:
            target = ROOT / item["path"]
            # Refuse to touch anything if path is no longer a real directory under the repository.
            if target.is_symlink() or not target.is_dir() or target.resolve().parent == ROOT.parent:
                continue
            before = item["bytes"]
            import shutil

            shutil.rmtree(target)
            removed.append({**item, "removed_bytes": before})
    report = {
        "root": str(ROOT),
        "branch": branch,
        "head": head,
        "dirty_worktree_entries": sum(bool(x) for x in dirty),
        "tracked_files": len(tracked),
        "untracked_files": len(untracked),
        "safe_cache_candidates": candidates,
        "removed_caches": removed,
        "candidate_bytes": sum(x["bytes"] for x in candidates),
        "removed_bytes_estimate": sum(x["removed_bytes"] for x in removed),
        "policy": "Report-only by default; never delete source, data, reports, evidence, build dirs, envs, or git-tracked/untracked files.",
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"QROS hygiene | branch={branch} | HEAD={head}")
        print(
            f"tracked={len(tracked)} untracked={len(untracked)} dirty_entries={report['dirty_worktree_entries']}"
        )
        print("Safe derived cache candidates:")
        for item in candidates:
            print(f"  {item['bytes'] / 1024 / 1024:8.2f} MB  {item['path']}")
        print(f"Total candidate cache bytes: {report['candidate_bytes'] / 1024 / 1024:.2f} MB")
        if args.clean_caches:
            print(
                f"Removed cache bytes (estimate): {report['removed_bytes_estimate'] / 1024 / 1024:.2f} MB"
            )
        print(report["policy"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
