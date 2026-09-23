#!/usr/bin/env python3
"""Verify a PostgreSQL backup can be restored into a disposable container."""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
from pathlib import Path


def run(cmd: list[str], **kwargs: object) -> None:
    subprocess.run(cmd, check=True, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("QROS_BACKUP_DATABASE_URL"))
    parser.add_argument("--output", type=Path, default=Path("backup/qros.dump"))
    parser.add_argument("--skip-restore", action="store_true")
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("QROS_BACKUP_DATABASE_URL or --database-url is required")
    for tool in ("pg_dump", "psql"):
        if shutil.which(tool) is None:
            raise SystemExit(f"{tool} is required")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    run(["pg_dump", "--format=custom", "--no-owner", "--file", str(args.output), args.database_url])
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    size = args.output.stat().st_size
    if size <= 0:
        raise SystemExit("backup is empty")

    report = {"backup": str(args.output), "bytes": size, "sha256": digest, "restored": False}
    if not args.skip_restore:
        if shutil.which("docker") is None:
            raise SystemExit("docker is required for restore verification")
        name = "qros-backup-verify"
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
        try:
            run(["docker", "run", "-d", "--name", name, "-e", "POSTGRES_PASSWORD=qros", "postgres:17"])
            for _ in range(60):
                probe = subprocess.run(
                    ["docker", "exec", name, "pg_isready", "-U", "postgres"],
                    capture_output=True,
                )
                if probe.returncode == 0:
                    break
            else:
                raise SystemExit("temporary postgres did not become ready")
            run(
                [
                    "pg_restore",
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--dbname",
                    "postgresql://postgres:qros@127.0.0.1:5432/postgres",
                    str(args.output),
                ]
            )
            report["restored"] = True
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
