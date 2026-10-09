#!/usr/bin/env python3
"""Fail-closed comparison of repository SQL migrations and an exported DB ledger.

Ledger CSV columns: version,name (as returned by Supabase migration history).
This tool reports drift; it never edits the database or migration files.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path


PREFIX = re.compile(r"^\d+_")


def logical_name(value: str) -> str:
    value = Path(value).name
    if value.endswith(".sql"):
        value = value[:-4]
    return PREFIX.sub("", value)


def read_ledger(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"version", "name"}.issubset(reader.fieldnames):
            raise ValueError("ledger CSV must contain version,name columns")
        rows = []
        for row in reader:
            version, name = (row.get("version") or "").strip(), (row.get("name") or "").strip()
            if not version or not name:
                raise ValueError("ledger contains an empty version or name")
            rows.append({"version": version, "name": name})
        return rows


def audit(migration_dir: Path, ledger: list[dict[str, str]]) -> list[str]:
    files = sorted(migration_dir.glob("*.sql"))
    repo_by_name: dict[str, list[Path]] = defaultdict(list)
    db_by_name: dict[str, list[dict[str, str]]] = defaultdict(list)
    for file in files:
        repo_by_name[logical_name(file.name)].append(file)
    for row in ledger:
        db_by_name[logical_name(row["name"])].append(row)

    findings: list[str] = []
    for name, paths in sorted(repo_by_name.items()):
        if len(paths) > 1:
            findings.append("DUPLICATE_REPO_LOGICAL_NAME: " + name + " => " + ", ".join(p.name for p in paths))
    for name, rows in sorted(db_by_name.items()):
        if len(rows) > 1:
            findings.append("DUPLICATE_DB_LOGICAL_NAME: " + name + " => " + ", ".join(r["version"] for r in rows))

    for name in sorted(repo_by_name.keys() - db_by_name.keys()):
        findings.append("REPO_ONLY_REQUIRES_SCHEMA_REVIEW: " + ", ".join(p.name for p in repo_by_name[name]))
    for name in sorted(db_by_name.keys() - repo_by_name.keys()):
        findings.append("DB_ONLY_REQUIRES_HISTORY_REVIEW: " + ", ".join(f'{r["version"]}:{r["name"]}' for r in db_by_name[name]))

    for name in sorted(repo_by_name.keys() & db_by_name.keys()):
        if len(repo_by_name[name]) == 1 and len(db_by_name[name]) == 1:
            repo_version = repo_by_name[name][0].name.split("_", 1)[0]
            db_version = db_by_name[name][0]["version"]
            if repo_version != db_version:
                findings.append(
                    f"VERSION_MISMATCH_REQUIRES_PROVENANCE_REVIEW: {name} "
                    f"repo={repo_version} db={db_version}"
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrations-dir", type=Path, default=Path("supabase/migrations"))
    parser.add_argument("--ledger", required=True, type=Path, help="CSV export with version,name columns")
    args = parser.parse_args()
    try:
        if not args.migrations_dir.is_dir():
            raise ValueError(f"migration directory does not exist: {args.migrations_dir}")
        findings = audit(args.migrations_dir, read_ledger(args.ledger))
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Migration files: {len(list(args.migrations_dir.glob('*.sql')))}")
    print(f"Database ledger rows: {len(read_ledger(args.ledger))}")
    if not findings:
        print("PASS: no filename/version drift detected (schema equivalence is not proven).")
        return 0
    for finding in findings:
        print(finding)
    print(f"FAIL: {len(findings)} drift finding(s); review manually. No changes applied.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
