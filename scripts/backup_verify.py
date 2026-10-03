"""Verify a PostgreSQL backup can be restored and passes QROS DR invariants.

The command intentionally uses the native PostgreSQL tools:
- pg_dump creates a custom-format logical backup.
- pg_restore loads it into a newly-created database.
- check_migrations.py validates migration ordering/integrity.
- the tenant-isolation pgTAP SQL is executed against the restored database.
- dataset object content hashes are compared before/after when object roots are supplied.

Example:
    python scripts/backup_verify.py \
      --source-url "$SOURCE_DATABASE_URL" \
      --target-admin-url "$TARGET_ADMIN_DATABASE_URL" \
      --object-root-before ./objects/source \
      --object-root-after ./objects/restored

For CI, the source and target can be two local PostgreSQL databases. The target
database is created and dropped by this script unless --keep-target is set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
TENANT_TEST = ROOT / "supabase" / "tests" / "tenant_isolation_test.sql"


def run(command: Sequence[str], *, env: dict[str, str] | None = None) -> None:
    printable = " ".join(shlex.quote(part) for part in command)
    print(f"+ {printable}")
    subprocess.run(command, check=True, cwd=ROOT, env=env)


def target_database_url(admin_url: str, database: str) -> str:
    parts = urlsplit(admin_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.pop("dbname", None)
    return urlunsplit(
        (parts.scheme, parts.netloc, f"/{database}", urlencode(query), parts.fragment)
    )


def database_name(database_url: str) -> str:
    path = urlsplit(database_url).path.lstrip("/")
    if not path:
        raise ValueError("database URL must include a database name")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_hashes(root: Path) -> dict[str, str]:
    if not root.is_dir():
        raise SystemExit(f"object root does not exist: {root}")
    return {
        str(path.relative_to(root)).replace(os.sep, "/"): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def verify_object_replication(before: Path | None, after: Path | None) -> None:
    if before is None and after is None:
        print("object replication: skipped (no object roots supplied)")
        return
    if before is None or after is None:
        raise SystemExit("--object-root-before and --object-root-after must be supplied together")

    before_hashes = object_hashes(before)
    after_hashes = object_hashes(after)
    if before_hashes != after_hashes:
        missing = sorted(set(before_hashes) - set(after_hashes))
        extra = sorted(set(after_hashes) - set(before_hashes))
        changed = sorted(
            path
            for path in set(before_hashes) & set(after_hashes)
            if before_hashes[path] != after_hashes[path]
        )
        raise SystemExit(
            "object replication hash mismatch: "
            f"missing={missing}, extra={extra}, changed={changed}"
        )
    print(f"object replication: OK ({len(before_hashes)} objects, SHA-256 matched)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", required=True, help="source PostgreSQL connection URL")
    parser.add_argument(
        "--target-admin-url",
        required=True,
        help="PostgreSQL URL used to create/drop the fresh restore database",
    )
    parser.add_argument(
        "--pg-dump",
        default="pg_dump",
        help="pg_dump executable (default: pg_dump)",
    )
    parser.add_argument(
        "--pg-restore",
        default="pg_restore",
        help="pg_restore executable (default: pg_restore)",
    )
    parser.add_argument(
        "--psql",
        default="psql",
        help="psql executable (default: psql)",
    )
    parser.add_argument(
        "--target-db",
        default=None,
        help="fresh database name; defaults to a temporary qros_dr_<pid> database",
    )
    parser.add_argument(
        "--object-root-before",
        type=Path,
        default=None,
        help="local mirror of source object storage",
    )
    parser.add_argument(
        "--object-root-after",
        type=Path,
        default=None,
        help="local mirror of restored object storage",
    )
    parser.add_argument(
        "--keep-target",
        action="store_true",
        help="keep the restored database for post-failure inspection",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_db = args.target_db or f"qros_dr_{os.getpid()}"
    target_url = target_database_url(args.target_admin_url, target_db)
    dump_file: Path | None = None

    try:
        with tempfile.TemporaryDirectory(prefix="qros-backup-verify-") as tmp:
            dump_file = Path(tmp) / "qros.backup"

            # Capture a portable logical backup. pg_restore supports custom-format
            # archives and restores them directly into a named database.
            run(
                [
                    args.pg_dump,
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--file",
                    str(dump_file),
                    args.source_url,
                ]
            )

            # A fresh database is mandatory: restoring over an existing database
            # can hide missing objects or stale schema.
            run(["createdb", "--maintenance-db", args.target_admin_url, target_db])
            run(
                [
                    args.pg_restore,
                    "--no-owner",
                    "--no-acl",
                    "--exit-on-error",
                    "--dbname",
                    target_url,
                    str(dump_file),
                ]
            )

            # Migration verification is intentionally run after restore so the
            # repository's migration contract is part of the DR gate.
            run(["python", str(ROOT / "scripts" / "check_migrations.py")])

            # pgTAP tenant isolation runs against the restored database itself.
            run(
                [
                    args.psql,
                    target_url,
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-f",
                    str(TENANT_TEST),
                ]
            )

            verify_object_replication(args.object_root_before, args.object_root_after)
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "target_database": target_db,
                        "backup_format": "custom",
                        "migration_verification": "passed",
                        "tenant_isolation": "passed",
                    },
                    sort_keys=True,
                )
            )
            return 0
    finally:
        if not args.keep_target:
            subprocess.run(
                ["dropdb", "--if-exists", "--maintenance-db", args.target_admin_url, target_db],
                check=False,
                cwd=ROOT,
            )


if __name__ == "__main__":
    raise SystemExit(main())
