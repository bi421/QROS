from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci" / "production_forward_migration.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "production-forward-migration.yml"

ALLOWLIST = (
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
    assert "APPLY_MIGRATION" in text
    assert 'CONFIRM_APPLY:-} = "APPLY"' in text


def test_forward_migration_uses_isolated_single_file_bundle() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'mkdir -p "${bundle}/supabase/migrations"' in text
    assert 'cp "${migration_path}" "${bundle}/supabase/migrations/${MIGRATION_FILE}"' in text
    assert "--include-all" in text
    assert "--dry-run" in text
    assert "unexpected" in text


def test_workflow_is_manual_and_protected() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "environment: production" in text
    assert "permissions:" in text
    assert "contents: read" in text
    assert "20260928123000_dataset_version_storage_path_reconciliation.sql" in text
    assert "20260928124500_workspace_billing_admin_role_reconciliation.sql" in text
    assert "20260928120000_storage_authorization_workspace_membership_reconciliation.sql" in text
    assert 'type: boolean' in text
    assert 'type: string' in text
    assert "pvhdsngxyoiqhqwujfjt" in text


def test_allowlist_has_exactly_three_entries() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert sum(text.count(migration) for migration in ALLOWLIST) == 3
