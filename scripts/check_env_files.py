"""Reject tracked environment files such as .env and local secret variants."""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    paths = [item for item in result.stdout.decode("utf-8").split("\0") if item]
    forbidden = [
        path
        for path in paths
        if path == ".env"
        or path.startswith(".env.")
        or "/.env" in path
        or path.endswith("/.env")
    ]
    if forbidden:
        print("Forbidden tracked environment files:", file=sys.stderr)
        for path in forbidden:
            print(f"  {path}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
