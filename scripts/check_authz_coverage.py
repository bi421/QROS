#!/usr/bin/env python3
"""Check that workspace/tenant-bearing public tables have RLS and policies."""
from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-url", required=True)
    args = parser.parse_args()
    sql = """
SELECT c.relname,
       c.relrowsecurity,
       COALESCE((
         SELECT count(*) FROM pg_policies p
         WHERE p.schemaname = 'public' AND p.tablename = c.relname
       ), 0)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind = 'r'
  AND EXISTS (
      SELECT 1
      FROM information_schema.columns col
      WHERE col.table_schema = 'public'
        AND col.table_name = c.relname
        AND col.column_name IN ('workspace_id', 'tenant_id')
  )
ORDER BY c.relname;
"""
    p = subprocess.run(
        ["psql", args.db_url, "-At", "-F", "\t", "-c", sql],
        text=True,
        capture_output=True,
        check=False,
    )
    if p.returncode:
        print(p.stderr.strip(), file=sys.stderr)
        return p.returncode

    rows = [line.split("\t") for line in p.stdout.splitlines() if line.strip()]
    failures = [
        row
        for row in rows
        if len(row) != 3 or row[1] != "t" or int(row[2]) < 1
    ]
    print(f"workspace/tenant-bearing tables checked: {len(rows)}")
    if failures:
        for row in failures:
            print("AUTHZ FAILURE:", "\t".join(row), file=sys.stderr)
        return 1
    print("AUTHZ COVERAGE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
