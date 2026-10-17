"""Fail-closed parser for supabase migration list output."""
from __future__ import annotations

import re
import sys

_VERSION = re.compile(r"\d{8,}(?:[_-][A-Za-z0-9][A-Za-z0-9_.-]*)?")
_BORDER_CHARS = " +-\u2500\u2501\u253c"


def parse_migration_rows(text: str) -> list[tuple[str, str]]:
    """Return local/remote version pairs, retaining one-sided rows."""
    rows: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.replace("\u2502", "|").strip()
        if line.startswith("|") and line.endswith("|"):
            line = line[1:-1].strip()
        if not line or "|" not in line:
            continue
        columns = [part.strip().strip(_BORDER_CHARS) for part in line.split("|")]
        if len(columns) < 2:
            continue
        local, remote = columns[0], columns[1]
        local_is_version = bool(_VERSION.fullmatch(local))
        remote_is_version = bool(_VERSION.fullmatch(remote))
        if local_is_version or remote_is_version:
            rows.append((local if local_is_version else "", remote if remote_is_version else ""))
    return rows


def main() -> int:
    rows = parse_migration_rows(sys.stdin.read())
    if not rows:
        print("migration list contained no parseable migration rows", file=sys.stderr)
        return 1
    mismatches = [(local, remote) for local, remote in rows if not local or not remote or local != remote]
    if mismatches:
        for local, remote in mismatches:
            print(f"local={local or '<missing>'} remote={remote or '<missing>'}")
        print("production and repository migration histories differ", file=sys.stderr)
        return 1
    print(f"verified {len(rows)} migration version rows with exact local/remote equality")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
