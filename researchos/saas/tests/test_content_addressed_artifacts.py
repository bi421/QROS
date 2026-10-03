from pathlib import Path

MIGRATION = Path(__file__).parents[3] / "supabase" / "migrations" / "202609190030_saas_content_addressed_artifacts.sql"


def test_artifact_content_addressed_contract() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "artifact_content_addressed_path" in sql
    assert "storage_path = workspace_id::text || '/artifacts/' || content_sha256" in sql
    assert "idx_artifact_workspace_content_sha256" in sql
    assert "group by workspace_id, content_sha256" in sql


def test_artifact_content_addressed_migration_fails_closed_on_noncanonical_existing_rows() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "raise exception 'cannot enforce artifact content-addressed path" in sql
    assert "raise exception 'cannot enforce artifact content-addressed identity" in sql
