#!/usr/bin/env bash
set -euo pipefail

: "${SUPABASE_PROJECT_ID:?SUPABASE_PROJECT_ID is required}"
: "${SUPABASE_ACCESS_TOKEN:?SUPABASE_ACCESS_TOKEN is required}"
: "${SUPABASE_DB_PASSWORD:?SUPABASE_DB_PASSWORD is required}"

echo "== migration history parity =="
output="$(supabase migration list --linked 2>&1)"
printf '%s\n' "${output}"

python3 - "${output}" <<'PY'
import sys

text = sys.argv[1]
rows = []
for raw in text.splitlines():
    line = raw.replace("│", "|").strip()
    if not line or not line[:8].isdigit() or line[8:9] not in "_-":
        continue
    cols = [part.strip() for part in line.split("|")]
    if len(cols) < 2:
        raise SystemExit("migration list format could not be parsed safely")
    rows.append((cols[0], cols[1]))

if not rows:
    raise SystemExit("migration list contained no parseable migration rows")

mismatches = [(local, remote) for local, remote in rows if not local or not remote or local != remote]
if mismatches:
    for local, remote in mismatches:
        print(f"local={local} remote={remote}")
    raise SystemExit("production and repository migration histories differ")

print(f"verified {len(rows)} migration version rows with exact local/remote equality")
PY

echo "== db push dry-run =="
supabase db push --linked --dry-run

echo "== required production objects =="
supabase db query --linked <<'SQL'
do $$
begin
  if to_regclass('public.research_claim') is null then
    raise exception 'required object missing: public.research_claim';
  end if;
  if to_regclass('public.audit_event') is null then
    raise exception 'required object missing: public.audit_event';
  end if;
  if to_regclass('public.retention_deletion_operation') is null then
    raise exception 'required object missing: public.retention_deletion_operation';
  end if;
end
$$;
SQL

echo "== required RLS =="
supabase db query --linked <<'SQL'
do $$
declare
  missing_rls text;
begin
  select string_agg(format('%I.%I', n.nspname, c.relname), ', ' order by c.relname)
    into missing_rls
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public'
    and c.relkind = 'r'
    and c.relname in (
      'workspace','workspace_member','dataset','dataset_version',
      'research_run','artifact','evidence','research_claim',
      'audit_event','retention_deletion_operation'
    )
    and not c.relrowsecurity;
  if missing_rls is not null then
    raise exception 'RLS disabled on required tables: %', missing_rls;
  end if;
end
$$;
SQL

echo "Production schema parity gate completed."
