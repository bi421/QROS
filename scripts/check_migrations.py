"""Validate the repository's canonical Supabase migration layout.

This is a static integrity gate only. It never connects to a database.
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS = Path("supabase/migrations")
NAME_RE = re.compile(r"^\d{12}_[a-z0-9][a-z0-9_-]*\.sql$")


def main() -> int:
    if not MIGRATIONS.is_dir():
        raise SystemExit("supabase/migrations directory is missing")

    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files:
        raise SystemExit("no Supabase migrations found")

    seen: set[str] = set()
    previous: str | None = None

    for path in files:
        if not NAME_RE.match(path.name):
            raise SystemExit(
                f"invalid migration filename: {path}; expected YYYYMMDDHHMM_description.sql"
            )

        prefix = path.name[:12]
        if prefix in seen:
            raise SystemExit(f"duplicate migration timestamp: {prefix}")
        seen.add(prefix)

        if previous is not None and prefix <= previous:
            raise SystemExit(f"migration ordering is not strictly increasing: {path}")
        previous = prefix

        data = path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            raise SystemExit(f"migration contains UTF-8 BOM: {path}")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SystemExit(f"migration is not valid UTF-8: {path}") from exc

    print(f"migration integrity OK: {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
