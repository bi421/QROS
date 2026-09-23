"""Verify a PostgreSQL backup by restoring into a fresh database and replaying QROS migrations.

The verifier creates a logical pg_dump, creates a fresh database, applies every
repository migration to that database, restores the source data, verifies the
migration/RLS contract and tenant isolation, and compares dataset SHA-256
provenance before/after. Optional object-root hashes verify Storage replicas.
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


def query_dataset_hashes(database_url: str) -> dict[str, str]:
    sql = (
        "select dataset_id::text || ':' || version_no::text, content_sha256 "
        "from public.dataset_version "
        "where deleted_at is null order by 1;"
    )
    result = subprocess.run(
        ["psql", database_url, "-X", "-At", "-F", "\t", "-c", sql],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    hashes: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, digest = line.split("\t", 1)
        hashes[key] = digest
    return hashes


def verify_dataset_hashes(source_url: str, restored_url: str) -> None:
    source = query_dataset_hashes(source_url)
    restored = query_dataset_hashes(restored_url)
    if source != restored:
        missing = sorted(set(source) - set(restored))
        extra = sorted(set(restored) - set(source))
        changed = sorted(
            key for key in set(source) & set(restored) if source[key] != restored[key]
        )
        raise SystemExit(
            "dataset SHA-256 mismatch: "
            f"missing={missing}, extra={extra}, changed={changed}"
        )
    print(f"dataset provenance: OK ({len(source)} versions, SHA-256 matched)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--target-admin-url", required=True)
    parser.add_argument("--pg-dump", default="pg_dump")
    parser.add_argument("--target-db", default=None)
    parser.add_argument("--object-root-before", type=Path, default=None)
    parser.add_argument("--object-root-after", type=Path, default=None)
    parser.add_argument("--keep-target", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_db = args.target_db or f"qros_dr_{os.getpid()}"
    target_url = target_database_url(args.target_admin_url, target_db)

    with tempfile.TemporaryDirectory(prefix="qros-backup-verify-") as tmp:
        dump_file = Path(tmp) / "qros-public-data.backup"
        try:
            # Supabase recommends the session pooler/direct connection for
            # migration work; public-only data avoids managed auth/storage schemas.
            run(
                [
                    args.pg_dump,
                    "--format=custom",
                    "--data-only",
                    "--schema=public",
                    "--table=auth.users",
                    "--no-owner",
                    "--no-acl",
                    "--file",
                    str(dump_file),
                    args.source_url,
                ]
            )

            run(["createdb", "--maintenance-db", args.target_admin_url, target_db])

            # The target schema is rebuilt exclusively from repository migrations.
            run(["supabase", "db", "push", "--db-url", target_url, "--include-all"])
            run(\n                [str(ROOT / "scripts" / "verify_migrations.py")],\n                env={**os.environ, "QROS_VERIFY_DATABASE_URL": target_url},\n            )

            # Restore source tenant data only after the exact migration set is applied.
            run(
                [
                    "pg_restore",
                    "--data-only",
                    "--no-owner",
                    "--no-acl",
                    "--exit-on-error",
                    "--dbname",
                    target_url,
                    str(dump_file),
                ]
            )

            verify_dataset_hashes(args.source_url, target_url)
            run(["supabase", "test", "db", str(TENANT_TEST), "--db-url", target_url])
            verify_object_replication(args.object_root_before, args.object_root_after)

            report = {
                "status": "PASS",
                "target_database": target_db,
                "backup_format": "custom",
                "migration_replay": "passed",
                "migration_verification": "passed",
                "tenant_isolation": "passed",
                "dataset_sha256": "passed",
                "storage_sha256": (
                    "passed" if args.object_root_before is not None else "skipped"
                ),
            }
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        finally:
            if not args.keep_target:
                subprocess.run(
                    [
                        "dropdb",
                        "--if-exists",
                        "--maintenance-db",
                        args.target_admin_url,
                        target_db,
                    ],
                    check=False,
                    cwd=ROOT,
                )


if __name__ == "__main__":
    raise SystemExit(main())
