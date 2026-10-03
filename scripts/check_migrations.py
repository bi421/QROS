"""Validate the repository's canonical Supabase migration layout.

This is a static integrity gate only. It never connects to a database.
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS = Path("supabase/migrations")
NAME_RE = re.compile(r"^\d{12}_[a-z0-9][a-z0-9_-]*\.sql$")

# Security assertions must never execute before the grants they assert are revoked.
# Keep this dependency explicit so timestamp changes cannot silently reintroduce a
# fresh-database security failure.
REQUIRED_MIGRATION_ORDER = (
    ("202609200000_r3_result_client_grants_deny.sql", "202609200003_r3_security_boundary_assertions_v2.sql"),
)


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

        lowered = path.name.lower()
        if any(token in lowered for token in ("_down", "down_", "rollback", "revert")):
            raise SystemExit(f"down/rollback migration is forbidden: {path}")
        text = path.read_text(encoding="utf-8")
        if re.search(r"^\\s*--\\s*(down migration|rollback)\\b", text, re.I | re.M):
            raise SystemExit(f"down/rollback marker is forbidden: {path}")

        data = path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            raise SystemExit(f"migration contains UTF-8 BOM: {path}")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SystemExit(f"migration is not valid UTF-8: {path}") from exc

    names = {path.name for path in files}
    for prerequisite, dependent in REQUIRED_MIGRATION_ORDER:
        if prerequisite not in names or dependent not in names:
            raise SystemExit(f"required security migration dependency missing: {prerequisite} -> {dependent}")
        if prerequisite >= dependent:
            raise SystemExit(f"security migration dependency order invalid: {prerequisite} must precede {dependent}")

    print(f"migration integrity OK: {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
