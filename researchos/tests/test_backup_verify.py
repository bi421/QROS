from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import backup_verify


def invoke(monkeypatch: pytest.MonkeyPatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["backup_verify.py", *args])
    return backup_verify.main()


def stub_backup_path(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if cmd[0] == "pg_dump":
            output = Path(cmd[cmd.index("--file") + 1])
            output.write_bytes(b"deterministic-test-dump")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(backup_verify, "require_tools", lambda _names: None)
    monkeypatch.setattr(backup_verify, "run", fake_run)
    monkeypatch.setattr(backup_verify, "psql", lambda _url, _sql: "16.4")
    monkeypatch.setattr(
        backup_verify,
        "database_snapshot",
        lambda _url: {
            "required_tables": sorted(backup_verify.REQUIRED_TABLES),
            "rls": [f"{table}=enabled" for table in sorted(backup_verify.REQUIRED_TABLES)],
            "dataset_versions": ["dataset-version-1"],
            "critical_counts": {table: 1 for table in backup_verify.CRITICAL_COUNT_TABLES},
        },
    )
    return calls


def test_missing_source_environment_fails_before_pg_dump(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("external backup tooling must not run")

    monkeypatch.delenv("QROS_BACKUP_SOURCE_ENVIRONMENT", raising=False)
    monkeypatch.setattr(backup_verify, "require_tools", fail_if_called)

    with pytest.raises(SystemExit, match="source environment is not explicitly authorized"):
        invoke(
            monkeypatch,
            "--database-url",
            "postgresql://postgres:secret@localhost:5432/qros",
        )

    assert not called


def test_production_source_fails_before_pg_dump(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("production source must be rejected before tooling")

    monkeypatch.setattr(backup_verify, "require_tools", fail_if_called)

    with pytest.raises(SystemExit, match="production is not an authorized source"):
        invoke(
            monkeypatch,
            "--source-environment",
            "production",
            "--database-url",
            "postgresql://postgres:secret@prod.example/qros",
        )

    assert not called


def test_explicit_staging_source_reaches_existing_backup_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = stub_backup_path(monkeypatch)
    report = tmp_path / "report.json"

    assert (
        invoke(
            monkeypatch,
            "--source-environment",
            "staging",
            "--database-url",
            "postgresql://postgres:secret@staging.example/qros",
            "--output",
            str(tmp_path / "qros.dump"),
            "--report",
            str(report),
            "--skip-restore",
        )
        == 0
    )

    assert any(command[0] == "pg_dump" for command in calls)
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "BACKUP_ONLY"
    assert payload["evidence_manifest"]["source"]["environment"] == "staging"


def test_skip_restore_does_not_bypass_source_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("external backup tooling must not run")

    monkeypatch.setattr(backup_verify, "require_tools", fail_if_called)

    with pytest.raises(SystemExit, match="source environment is not explicitly authorized"):
        invoke(
            monkeypatch,
            "--database-url",
            "postgresql://postgres:secret@localhost:5432/qros",
            "--skip-restore",
        )

    assert not called


def test_existing_restore_validation_remains_intact_and_manifest_records_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = stub_backup_path(monkeypatch)
    source_snapshot = {
        "required_tables": sorted(backup_verify.REQUIRED_TABLES),
        "rls": [f"{table}=enabled" for table in sorted(backup_verify.REQUIRED_TABLES)],
        "dataset_versions": ["dataset-version-1"],
        "critical_counts": {table: 1 for table in backup_verify.CRITICAL_COUNT_TABLES},
    }
    monkeypatch.setattr(backup_verify, "database_snapshot", lambda _url: source_snapshot)

    def fake_subprocess_run(
        cmd: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if cmd[:2] == ["docker", "exec"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "verify_migrations.py" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout="migration/security verification OK", stderr=""
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(backup_verify.subprocess, "run", fake_subprocess_run)
    report = tmp_path / "report.json"

    assert (
        invoke(
            monkeypatch,
            "--source-environment",
            "local",
            "--source-project-ref",
            "local-test",
            "--source-release-sha",
            "abc123",
            "--evidence-id",
            "dr-test-001",
            "--database-url",
            "postgresql://postgres:secret@localhost:5432/qros",
            "--output",
            str(tmp_path / "qros.dump"),
            "--report",
            str(report),
        )
        == 0
    )

    assert any(command[0] == "pg_dump" for command in calls)
    assert any(command[0] == "pg_restore" for command in calls)
    payload = json.loads(report.read_text(encoding="utf-8"))
    manifest = payload["evidence_manifest"]
    assert payload["status"] == "VERIFIED"
    assert manifest["evidence_id"] == "dr-test-001"
    assert manifest["restore"]["status"] == "VERIFIED"
    assert manifest["verification"]["migration_security"] == "VERIFIED"
    assert manifest["verification"]["required_tables"]["restore"] == "VERIFIED"
    assert manifest["verification"]["rls_security"]["restore"] == "VERIFIED"
    assert manifest["verification"]["dataset_version_integrity"]["restore"] == "VERIFIED"
    assert manifest["verification"]["critical_record_counts"]["restore"] == "VERIFIED"
    assert manifest["verification"]["tenant_isolation_recovery"] == "NOT_EXECUTED"
    assert manifest["verification"]["storage_recovery"] == "NOT_EXECUTED"
    assert manifest["verification"]["queue_recovery"] == "NOT_EXECUTED"
    assert manifest["verification"]["application_recovery"] == "NOT_EXECUTED"
    assert manifest["rpo_rto"]["status"] == "NOT_EXECUTED"


def test_manifest_does_not_persist_connection_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    stub_backup_path(monkeypatch)
    report = tmp_path / "report.json"
    secret_url = "postgresql://postgres:super-secret-token@staging.example/qros"

    assert (
        invoke(
            monkeypatch,
            "--source-environment",
            "staging",
            "--source-project-ref",
            "staging-project",
            "--database-url",
            secret_url,
            "--output",
            str(tmp_path / "qros.dump"),
            "--report",
            str(report),
            "--skip-restore",
        )
        == 0
    )

    report_text = report.read_text(encoding="utf-8")
    assert "super-secret-token" not in report_text
    assert secret_url not in report_text
    payload = json.loads(report_text)
    assert payload["evidence_manifest"]["source"]["project_ref"] == "staging-project"
