from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci" / "production_forward_migration.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "production-forward-migration.yml"

ALLOWLIST = (
    "202610060001_production_forward_reconciliation.sql",
    "20260928123000_dataset_version_storage_path_reconciliation.sql",
    "20260928124500_workspace_billing_admin_role_reconciliation.sql",
    "20260928120000_storage_authorization_workspace_membership_reconciliation.sql",
)


def test_forward_migration_script_exists_and_is_strict() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text
    for migration in ALLOWLIST:
        assert migration in text
    assert "migration repair" not in text
    assert "schema_migrations" not in text
    assert "/v1/projects/" not in text
    assert "SUPABASE_PROJECT_ID" in text
    assert "APPLY_MIGRATION" in text
    assert '${CONFIRM_APPLY:-}" = "APPLY"' in text


def test_forward_migration_uses_isolated_single_file_bundle() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'mkdir -p "${bundle}/supabase/migrations"' in text
    assert 'cp "${migration_path}" "${bundle}/supabase/migrations/${MIGRATION_FILE}"' in text
    assert "cp -r" not in text
    assert "cp supabase/migrations" not in text
    assert "cp supabase/config.toml" not in text
    assert "config.toml" not in text
    assert "--include-all" in text
    assert "--dry-run" in text
    assert "unexpected" in text


def test_workflow_is_manual_and_protected() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "push:" not in text
    assert "pull_request:" not in text
    assert "schedule:" not in text
    assert "environment: production" in text
    assert "permissions:" in text
    assert "contents: read" in text
    assert "SUPABASE_ACCESS_TOKEN" in text
    assert "PRODUCTION_DB_PASSWORD" in text
    assert "PRODUCTION_PROJECT_ID" in text
    assert 'test "${SUPABASE_PROJECT_ID}" = "pvhdsngxyoiqhqwujfjt"' in text
    assert "20260928123000_dataset_version_storage_path_reconciliation.sql" in text
    assert "20260928124500_workspace_billing_admin_role_reconciliation.sql" in text
    assert "20260928120000_storage_authorization_workspace_membership_reconciliation.sql" in text
    assert 'type: boolean' in text
    assert 'type: string' in text
    assert "pvhdsngxyoiqhqwujfjt" in text


def test_allowlist_has_exactly_four_entries_and_excludes_worker() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert all(script.count(migration) == 2 for migration in ALLOWLIST)
    assert sum(workflow.count(migration) for migration in ALLOWLIST) == 4
    assert "20260928103556_saas_worker_queue_consumer.sql" not in script
    assert "20260928103556_saas_worker_queue_consumer.sql" not in workflow


def test_mutation_requires_both_apply_and_confirmation() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'if [[ "${APPLY_MIGRATION:-false}" != "true" ]]; then' in text
    assert 'test "${CONFIRM_APPLY:-}" = "APPLY"' in text
    apply_guard = text.index('if [[ "${APPLY_MIGRATION:-false}" != "true" ]]; then')
    confirm_guard = text.index('test "${CONFIRM_APPLY:-}" = "APPLY"')
    apply_command = text.index('supabase --workdir "${bundle}" db push \\\n  --linked \\\n  --include-all \\\n  --yes')
    assert apply_guard < confirm_guard < apply_command


def test_exact_version_and_migration_specific_postconditions_are_verified() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'version="${MIGRATION_FILE%%_*}"' in text
    assert 'migration_version_verified=${version}' in text
    assert "dataset_version_storage_path_contract" in text
    assert "validate_dataset_version_storage_path()" in text
    assert "workspace_member_role_check" in text
    assert "billing_admin" in text
    assert "qros-datasets" in text
    assert "private.is_workspace_member" in text


def test_dry_run_precedes_any_mutating_db_push() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    dry_run = text.index('supabase --workdir "${bundle}" db push \\\n    --linked \\\n    --include-all \\\n    --dry-run')
    apply_push = text.index('supabase --workdir "${bundle}" db push \\\n  --linked \\\n  --include-all \\\n  --yes')
    assert dry_run < apply_push
    assert 'APPLY_MIGRATION:-false' in text
