#!/usr/bin/env python3
"""Verify QROS tenant-boundary migration invariants.

QROS uses workspace_id plus authenticated workspace membership as its tenant key.
This checker therefore verifies the actual architecture rather than inventing a
separate tenant_id column.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MIGRATIONS=ROOT/"supabase"/"migrations"
TENANT_TABLES={"dataset","dataset_version","research_run","artifact","evidence","usage_event","audit_log","subscription","workspace_member","research_run_result","research_run_artifact"}
TABLE_RE=re.compile(r"create table if not exists public\.([a-z_]+)",re.I)

def static_check() -> None:
    sql="\n".join(p.read_text(encoding="utf-8") for p in sorted(MIGRATIONS.glob("*.sql")))
    for table in sorted(TENANT_TABLES):
        if not re.search(rf"create table if not exists public\.{table}\s*\(",sql,re.I):
            raise SystemExit(f"missing table definition: {table}")
        if table not in {"workspace_member","subscription","dataset_version"} and not re.search(rf"create table if not exists public\.{table}.*?workspace_id\s+uuid",sql,re.I|re.S):
            raise SystemExit(f"missing workspace_id definition: {table}")
        if not re.search(rf"alter table public\.{table} enable row level security",sql,re.I):
            raise SystemExit(f"RLS not enabled in migration history: {table}")
    print(f"static migration security invariants OK: {len(TENANT_TABLES)} tenant tables")

def database_check(url: str) -> None:
    query="""
select tablename from pg_tables
where schemaname='public'
  and tablename in ('dataset','dataset_version','research_run','artifact','evidence','usage_event','audit_log','subscription','workspace_member')
  and rowsecurity = false;
"""
    p=subprocess.run(["psql",url,"-At","-c",query],text=True,capture_output=True,check=False)
    if p.returncode!=0:
        raise SystemExit(p.stderr.strip() or "psql failed")
    bad=[x for x in p.stdout.splitlines() if x.strip()]
    if bad:
        raise SystemExit("tables without RLS: "+", ".join(bad))
    print("database RLS check OK")

def main()->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--database-url")
    args=parser.parse_args()
    static_check()
    if args.database_url:
        database_check(args.database_url)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
