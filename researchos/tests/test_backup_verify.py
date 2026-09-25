from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import backup_verify

EXPECTED_TABLES = sorted(backup_verify.REQUIRED_TABLES)
EXPECTED_RLS = [f"{table}=enabled" for table in EXPECTED_TABLES]


def fake_psql(url: str, sql: str) -> str:
    if sql == "show server_version;":
        return "16.4"
    if "select c.relname from pg_class" in sql:
        return "\n".join(EXPECTED_TABLES)
    if "case when c.relrowsecurity" in sql:
        return "\n".join(EXPECTED_RLS)
    if "select id::text, dataset_id::text" in sql:
        return "dataset-version-id\tdataset-id\t1\tsha256-value"
    if sql.startswith("select count(*) from public."):
        return "0"
    raise AssertionError(f"unexpected SQL: {sql}")


def test_missing_source_environment_fails_before_pg_dump(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QROS_BACKUP_SOURCE_ENVIRONMENT", raising=False)
    monkeypatch.setattr(
        backup_verify, "run", lambda *args, **kwargs: pytest.fail("pg_dump must not run")
    )
    with pytest.raises(SystemExit, match="source environment is not explicitly authorized"):
        backup_verify.main(["--database-url", "postgresql://example/db"])


def test_production_source_fails_before_pg_dump(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        backup_verify, "run", lambda *args, **kwargs: pytest.fail("pg_dump must not run")
    )
    with pytest.raises(SystemExit, match="Production source targeting is not authorized"):
        backup_verify.main([
            "--database-url", "postgresql://prod.example/db",
            "--source-environment", "production",
        ])


def test_explicit_nonproduction_source_reaches_existing_backup_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(backup_verify, "require_tools", lambda names: None)
    monkeypatch.setattr(backup_verify, "psql", fake_psql)

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert cmd[0] == "pg_dump"
        Path(cmd[cmd.index("--file") + 1]).write_bytes(b"backup-bytes")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(backup_verify, "run", fake_run)
    report = tmp_path / "report.json"
    dump = tmp_path / "backup.dump"
    result = backup_verify.main([
        "--database-url", "postgresql://staging.example/db",
        "--source-environment", "staging",
        "--output", str(dump), "--report", str(report), "--skip-restore",
    ])
    assert result == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "BACKUP_ONLY"
    assert payload["restore"]["executed"] is False


def test_skip_restore_does_not_bypass_source_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QROS_BACKUP_SOURCE_ENVIRONMENT", raising=False)
    monkeypatch.setattr(
        backup_verify, "run", lambda *args, **kwargs: pytest.fail("pg_dump must not run")
    )
    with pytest.raises(SystemExit, match="--skip-restore does not make source selection safe"):
        backup_verify.main(["--database-url", "postgresql://example/db", "--skip-restore"])


def test_connection_secret_never_enters_existing_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(backup_verify, "require_tools", lambda names: None)
    monkeypatch.setattr(backup_verify, "psql", fake_psql)
    secret_url = "postgresql://backup-user:super-secret-token@staging.example/db"

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(cmd[cmd.index("--file") + 1]).write_bytes(b"backup-bytes")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(backup_verify, "run", fake_run)
    report = tmp_path / "report.json"
    backup_verify.main([
        "--database-url", secret_url, "--source-environment", "staging",
        "--output", str(tmp_path / "backup.dump"), "--report", str(report),
        "--skip-restore",
    ])
    text = report.read_text(encoding="utf-8")
    assert "super-secret-token" not in text
    assert secret_url not in text


def test_schema_validation_still_rejects_missing_required_table(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad_psql(url: str, sql: str) -> str:
        if "select c.relname from pg_class" in sql:
            return "\n".join(EXPECTED_TABLES[:-1])
        raise AssertionError("schema check should fail before other queries")
    monkeypatch.setattr(backup_verify, "psql", bad_psql)
    with pytest.raises(SystemExit, match="required schema mismatch"):
        backup_verify.database_snapshot("postgresql://recovery/db")


def test_schema_validation_still_rejects_disabled_rls(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad_psql(url: str, sql: str) -> str:
        if "select c.relname from pg_class" in sql:
            return "\n".join(EXPECTED_TABLES)
        if "case when c.relrowsecurity" in sql:
            return "\n".join(EXPECTED_RLS[:-1] + [f"{EXPECTED_TABLES[-1]}=disabled"])
        raise AssertionError("RLS check should fail before other queries")
    monkeypatch.setattr(backup_verify, "psql", bad_psql)
    with pytest.raises(SystemExit, match="RLS verification failed"):
        backup_verify.database_snapshot("postgresql://recovery/db")


def test_evidence_manifest_marks_unexecuted_controls_explicitly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(backup_verify, "require_tools", lambda names: None)
    monkeypatch.setattr(backup_verify, "psql", fake_psql)

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(cmd[cmd.index("--file") + 1]).write_bytes(b"backup-bytes")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(backup_verify, "run", fake_run)
    report = tmp_path / "report.json"
    backup_verify.main([
        "--database-url", "postgresql://staging.example/db",
        "--source-environment", "staging",
        "--source-project-ref", "staging-ref",
        "--source-release-sha", "abc123",
        "--source-migration-version", "37",
        "--evidence-id", "dr-manifest-001",
        "--output", str(tmp_path / "backup.dump"),
        "--report", str(report),
        "--skip-restore",
    ])

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 3
    assert payload["evidence"] == {
        "evidence_id": "dr-manifest-001",
        "source_environment": "staging",
        "source_project_ref": "staging-ref",
        "source_release_sha": "abc123",
        "source_migration_version": "37",
        "restore_target": None,
        "operator": {"signoff": "NOT_PROVIDED"},
    }
    assert payload["timeline"]["backup_started_at"]
    assert payload["timeline"]["backup_completed_at"]
    assert payload["checks"]["required_tables"]["status"] == "VERIFIED"
    assert payload["checks"]["rls_security"]["status"] == "VERIFIED"
    assert payload["checks"]["dataset_version_integrity"]["status"] == "PENDING_RESTORE"
    assert payload["checks"]["critical_governed_record_counts"]["status"] == "PENDING_RESTORE"
    assert payload["checks"]["migration_security"]["status"] == "PENDING_RESTORE"
    assert payload["checks"]["tenant_isolation_recovery"]["status"] == "NOT_EXECUTED"
    assert payload["checks"]["storage_recovery"]["status"] == "NOT_EXECUTED"
    assert payload["checks"]["queue_job_recovery"]["status"] == "NOT_EXECUTED"
    assert payload["checks"]["application_recovery"]["status"] == "NOT_EXECUTED"
    assert payload["rpo_rto"] == "NOT_EXECUTED"
    assert payload["recovery_measurements"] == {
        "rpo_seconds": None, "rto_seconds": None, "status": "NOT_EXECUTED"
    }


def test_evidence_manifest_never_persists_connection_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(backup_verify, "require_tools", lambda names: None)
    monkeypatch.setattr(backup_verify, "psql", fake_psql)
    secret_url = "postgresql://backup-user:super-secret-token@staging.example/db"

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(cmd[cmd.index("--file") + 1]).write_bytes(b"backup-bytes")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(backup_verify, "run", fake_run)
    report = tmp_path / "report.json"
    backup_verify.main([
        "--database-url", secret_url,
        "--source-environment", "staging",
        "--source-project-ref", "staging-ref",
        "--output", str(tmp_path / "backup.dump"),
        "--report", str(report),
        "--skip-restore",
    ])

    text = report.read_text(encoding="utf-8")
    assert "super-secret-token" not in text
    assert secret_url not in text
    assert "postgresql://" not in text


def test_source_environment_can_be_supplied_by_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QROS_BACKUP_SOURCE_ENVIRONMENT", "staging")
    monkeypatch.setattr(backup_verify, "require_tools", lambda names: None)
    monkeypatch.setattr(backup_verify, "psql", fake_psql)

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(cmd[cmd.index("--file") + 1]).write_bytes(b"backup-bytes")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(backup_verify, "run", fake_run)
    result = backup_verify.main([
        "--database-url", "postgresql://staging.example/db",
        "--output", str(tmp_path / "backup.dump"),
        "--report", str(tmp_path / "report.json"),
        "--skip-restore",
    ])
    assert result == 0


def test_production_source_environment_variable_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QROS_BACKUP_SOURCE_ENVIRONMENT", "production")
    monkeypatch.setattr(
        backup_verify, "run", lambda *args, **kwargs: pytest.fail("pg_dump must not run")
    )
    with pytest.raises(SystemExit, match="Production source targeting is not authorized"):
        backup_verify.main(["--database-url", "postgresql://prod.example/db"])
