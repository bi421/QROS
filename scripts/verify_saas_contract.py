#!/usr/bin/env python3
"""Fail-closed verification of the live QROS SaaS database contract."""
from __future__ import annotations

import argparse
import json
import subprocess


REQUIRED_SQL = """
select json_build_object(
  'entitlement_table', to_regclass('public.entitlement') is not null,
  'provision_workspace', to_regprocedure('public.provision_workspace(uuid,text)') is not null,
  'process_billing_event_10', to_regprocedure(
      'public.process_billing_event(text,uuid,text,text,text,text,timestamptz,text,text,timestamptz)'
  ) is not null,
  'billing_event_created_at', exists(
      select 1 from information_schema.columns
      where table_schema='public' and table_name='billing_event'
        and column_name='provider_event_created_at'
  ),
  'subscription_last_billing_event_at', exists(
      select 1 from information_schema.columns
      where table_schema='public' and table_name='subscription'
        and column_name='last_billing_event_at'
  ),
  'dataset_storage_contract', exists(
      select 1 from pg_constraint
      where conname='dataset_version_storage_path_contract'
  ),
  'workspace_deleted_at', exists(
      select 1 from information_schema.columns
      where table_schema='public' and table_name='workspace'
        and column_name='deleted_at'
  ),
  'workspace_purge_at', exists(
      select 1 from information_schema.columns
      where table_schema='public' and table_name='workspace'
        and column_name='purge_at'
  ),
  'soft_delete_workspace', to_regprocedure(
      'public.soft_delete_workspace(uuid,timestamptz,integer)'
  ) is not null,
  'purge_deleted_workspaces', to_regprocedure(
      'public.purge_deleted_workspaces(timestamptz)'
  ) is not null,
  'billing_admin_role_check', exists(
      select 1 from pg_constraint
      where conname='workspace_member_role_check'
        and pg_get_constraintdef(oid) ilike '%billing_admin%'
  ),
  'storage_tenant_policies', (
      select count(*) from pg_policies
      where schemaname='storage' and tablename='objects'
        and policyname in (
          'qros_datasets_tenant_insert',
          'qros_datasets_tenant_select',
          'qros_datasets_tenant_update',
          'qros_datasets_tenant_delete'
        )
  ) = 4,
  'legacy_storage_tenant_id_policies', (
      select count(*) from pg_policies
      where schemaname='storage' and tablename='objects'
        and (
          coalesce(qual,'') ilike '%tenant_id%'
          or coalesce(with_check,'') ilike '%tenant_id%'
        )
  )
) as audit;
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()

    result = subprocess.run(
        ["psql", args.database_url, "-At", "-c", REQUIRED_SQL],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "psql failed")

    raw = result.stdout.strip()
    if not raw:
        raise SystemExit("SaaS contract audit returned no result")

    print(raw)
    audit = json.loads(raw)["audit"]
    expected = {
        "entitlement_table": True,
        "provision_workspace": True,
        "process_billing_event_10": True,
        "billing_event_created_at": True,
        "subscription_last_billing_event_at": True,
        "dataset_storage_contract": True,
        "workspace_deleted_at": True,
        "workspace_purge_at": True,
        "soft_delete_workspace": True,
        "purge_deleted_workspaces": True,
        "billing_admin_role_check": True,
        "storage_tenant_policies": True,
        "legacy_storage_tenant_id_policies": 0,
    }
    failures = [
        f"{key}={audit.get(key)!r} (expected {value!r})"
        for key, value in expected.items()
        if audit.get(key) != value
    ]
    if failures:
        raise SystemExit(
            "SaaS staging contract FAILED: " + "; ".join(failures)
        )

    print("SaaS staging contract OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
