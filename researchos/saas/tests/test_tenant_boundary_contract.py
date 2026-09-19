from pathlib import Path

MIGRATION = Path(__file__).parents[3] / "supabase" / "migrations" / "202609190023_saas_tenant_boundary_v2.sql"


def test_tenant_boundary_migration_pins_security_definer_search_path() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "security definer\nset search_path = ''" in sql
    assert "revoke all on function public.enforce_research_run_workspace()" in sql
    assert "revoke all on function public.enforce_run_child_workspace()" in sql


def test_tenant_boundary_covers_every_research_run_child_table() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for trigger in (
        "trg_artifact_workspace",
        "trg_evidence_workspace",
        "trg_usage_event_workspace",
        "trg_research_run_result_workspace",
        "trg_research_run_artifact_workspace",
    ):
        assert f"create trigger {trigger}" in sql


def test_tenant_boundary_checks_parent_workspace() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "where rr.id = new.research_run_id" in sql
    assert "and rr.workspace_id = new.workspace_id" in sql
    assert "where dv.id = new.dataset_version_id" in sql
    assert "and d.workspace_id = new.workspace_id" in sql
