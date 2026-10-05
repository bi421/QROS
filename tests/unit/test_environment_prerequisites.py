from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_environment_prerequisites.py"


def load_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("qros_external_preflight", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_staging_requires_all_three_controlled_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    audit = load_module()
    for name in audit.PROFILES["staging"]:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(SystemExit, match="missing required variables"):
        audit._required("staging")


def test_staging_rejects_shared_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    audit = load_module()
    monkeypatch.setenv("QROS_STAGING_BASE_URL", "https://staging.example")
    monkeypatch.setenv("QROS_STAGING_JWT", "same")
    monkeypatch.setenv("QROS_STAGING_ISOLATION_JWT", "same")
    audit._required("staging")

    with pytest.raises(SystemExit, match="must be distinct"):
        audit._validate_staging()


@pytest.mark.parametrize(
    "url",
    [
        "http://staging.example",
        "https://user:pass@staging.example",
        "https://staging.example?token=secret",
        "https://staging.example/#secret",
    ],
)
def test_staging_rejects_non_bare_https_origin(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    audit = load_module()
    monkeypatch.setenv("QROS_STAGING_BASE_URL", url)
    monkeypatch.setenv("QROS_STAGING_JWT", "primary")
    monkeypatch.setenv("QROS_STAGING_ISOLATION_JWT", "isolation")
    audit._required("staging")

    with pytest.raises(SystemExit, match="bare HTTPS origin"):
        audit._validate_staging()


def test_staging_accepts_bare_https_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    audit = load_module()
    monkeypatch.setenv("QROS_STAGING_BASE_URL", "https://staging.example")
    monkeypatch.setenv("QROS_STAGING_JWT", "primary")
    monkeypatch.setenv("QROS_STAGING_ISOLATION_JWT", "isolation")
    audit._required("staging")
    audit._validate_staging()


def test_dr_rejects_production_target(monkeypatch: pytest.MonkeyPatch) -> None:
    audit = load_module()
    values = {
        "QROS_BACKUP_SOURCE_ENVIRONMENT": "staging",
        "QROS_STAGING_SUPABASE_PROJECT_REF": "stage-ref",
        "QROS_STAGING_SUPABASE_URL": "https://stage.supabase.co",
        "QROS_STAGING_SUPABASE_SERVICE_ROLE_KEY": "secret",
        "QROS_RECOVERY_TARGET_ENVIRONMENT": "production",
        "QROS_RECOVERY_TARGET_ID": "recovery-ref",
        "QROS_RECOVERY_S3_BUCKET": "bucket",
        "QROS_RECOVERY_AWS_REGION": "region",
        "QROS_RECOVERY_AWS_ACCESS_KEY_ID": "key",
        "QROS_RECOVERY_AWS_SECRET_ACCESS_KEY": "secret",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    audit._required("dr")

    with pytest.raises(SystemExit, match="isolated"):
        audit._validate_dr()


def test_dr_rejects_target_identity_equal_to_staging(monkeypatch: pytest.MonkeyPatch) -> None:
    audit = load_module()
    values = {
        "QROS_BACKUP_SOURCE_ENVIRONMENT": "staging",
        "QROS_STAGING_SUPABASE_PROJECT_REF": "same-ref",
        "QROS_STAGING_SUPABASE_URL": "https://stage.supabase.co",
        "QROS_STAGING_SUPABASE_SERVICE_ROLE_KEY": "secret",
        "QROS_RECOVERY_TARGET_ENVIRONMENT": "recovery",
        "QROS_RECOVERY_TARGET_ID": "same-ref",
        "QROS_RECOVERY_S3_BUCKET": "bucket",
        "QROS_RECOVERY_AWS_REGION": "region",
        "QROS_RECOVERY_AWS_ACCESS_KEY_ID": "key",
        "QROS_RECOVERY_AWS_SECRET_ACCESS_KEY": "secret",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    audit._required("dr")

    with pytest.raises(SystemExit, match="differ from staging"):
        audit._validate_dr()


def test_production_migration_rejects_wrong_project(monkeypatch: pytest.MonkeyPatch) -> None:
    audit = load_module()
    monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "secret")
    monkeypatch.setenv("PRODUCTION_DB_PASSWORD", "secret")
    monkeypatch.setenv("PRODUCTION_PROJECT_ID", "wrong")
    audit._required("production-migration")

    with pytest.raises(SystemExit, match="governed QROS production target"):
        audit._validate_production_migration()
