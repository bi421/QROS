from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"

STORAGE = MIGRATIONS / "20261010000100_storage_authorization_workspace_membership_reconciliation.sql"
DATASET_VERSION = MIGRATIONS / "20261010000200_dataset_version_storage_path_reconciliation.sql"
SERVER_ONLY = MIGRATIONS / "20261010000300_restore_server_only_research_projections.sql"


def test_storage_forward_migration_fails_closed_before_replacing_policies() -> None:
    sql = STORAGE.read_text(encoding="utf-8")
    assert "qros-datasets" in sql
    assert "expected exactly four target policies" in sql
    assert "roles::text = '{authenticated}'" in sql
    assert "private.is_workspace_member" in sql
    assert "Storage reconciliation precondition failed" in sql


def test_storage_forward_migration_uses_workspace_membership_not_jwt_tenant_claims() -> None:
    sql = STORAGE.read_text(encoding="utf-8")
    policy_start = sql.index("drop policy qros_datasets_tenant_select on storage.objects;")
    policy_end = sql.index(chr(10) + "do $$", policy_start)
    policy_replacement = sql[policy_start:policy_end]
    assert policy_replacement.count("private.is_workspace_member") >= 5
    assert "auth.jwt()" not in policy_replacement
    assert "tenant_id" not in policy_replacement
    assert "Storage reconciliation postcondition failed: JWT tenant authorization remains" in sql


def test_dataset_version_forward_migration_rejects_invalid_existing_paths() -> None:
    sql = DATASET_VERSION.read_text(encoding="utf-8")
    assert "existing rows violate canonical path syntax" in sql
    assert "^tenant/[0-9a-f-]{36}/datasets/[0-9a-f]{64}/[1-9][0-9]*/$" in sql
    assert "dataset_workspace uuid" in sql
    assert "select d.workspace_id" in sql
    assert "new.content_sha256 <> lower(new.content_sha256)" in sql
    assert "new.storage_path <> format(" in sql


def test_dataset_version_forward_migration_reasserts_constraint_and_trigger() -> None:
    sql = DATASET_VERSION.read_text(encoding="utf-8")
    assert "drop constraint if exists dataset_version_storage_path_contract" in sql
    assert "add constraint dataset_version_storage_path_contract" in sql
    assert "create or replace function public.validate_dataset_version_storage_path()" in sql
    assert "create trigger dataset_version_storage_path_contract" in sql


def test_server_only_forward_migration_requires_forced_rls_before_mutation() -> None:
    sql = SERVER_ONLY.read_text(encoding="utf-8")
    precondition = sql[:sql.index("drop policy if exists tenant_select on public.research_validation;")]
    assert "c.relrowsecurity" in precondition
    assert "c.relforcerowsecurity" in precondition
    assert "unexpected policy exists" in precondition
    assert "server-only reconciliation blocked" in precondition


def test_server_only_forward_migration_removes_client_grants_and_tenant_policies() -> None:
    sql = SERVER_ONLY.read_text(encoding="utf-8")
    for table in ("research_validation", "research_finding"):
        assert f"drop policy if exists tenant_select on public.{table}" in sql
        assert f"drop policy if exists tenant_insert on public.{table}" in sql
        assert f"drop policy if exists tenant_update on public.{table}" in sql
        assert f"drop policy if exists tenant_delete on public.{table}" in sql
    assert "revoke all on table public.research_validation, public.research_finding" in sql
    assert "from public, anon, authenticated" in sql


def test_server_only_forward_migration_reasserts_explicit_client_deny_and_postconditions() -> None:
    sql = SERVER_ONLY.read_text(encoding="utf-8")
    assert "research validation client deny" in sql
    assert "research finding client deny" in sql
    assert "using (false)" in sql
    assert "with check (false)" in sql
    assert "client_policy_count <> 1" in sql
    assert "server-only reconciliation postcondition failed" in sql


def test_forward_migration_sources_are_distinct_append_only_files() -> None:
    assert STORAGE.is_file()
    assert DATASET_VERSION.is_file()
    assert SERVER_ONLY.is_file()
    assert len({STORAGE.name, DATASET_VERSION.name, SERVER_ONLY.name}) == 3
    assert all(path.name[:14].isdigit() for path in (STORAGE, DATASET_VERSION, SERVER_ONLY))
