from pathlib import Path
import importlib.util


ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "ops" / "release" / "readiness_audit.py"


def load_audit():
    spec = importlib.util.spec_from_file_location(
        "qros_readiness_audit",
        AUDIT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_known_fail_open_install_is_rejected():
    audit = load_audit()
    failures: list[str] = []

    audit.check_workflow_fail_open(
        ".github/workflows/production-db-backup.yml",
        "python -m pip install -e . || true\n",
        failures,
    )

    assert len(failures) == 1
    assert "fail-open" in failures[0]


def test_exit_zero_quality_gate_is_rejected():
    audit = load_audit()
    failures: list[str] = []

    audit.check_workflow_fail_open(
        ".github/workflows/staging-performance-gate.yml",
        "ruff check . --exit-zero\n",
        failures,
    )

    assert len(failures) == 1
    assert "fail-open" in failures[0]


def test_storage_cleanup_suppression_is_rejected():
    audit = load_audit()
    failures: list[str] = []

    audit.check_workflow_fail_open(
        ".github/workflows/storage-recovery-drill.yml",
        'aws s3 rm "s3://bucket/object" || true\n',
        failures,
    )

    assert len(failures) == 1
    assert "fail-open" in failures[0]


def test_governed_workflow_with_clean_commands_passes():
    audit = load_audit()
    failures: list[str] = []

    audit.check_workflow_fail_open(
        ".github/workflows/production-db-backup.yml",
        "set -euo pipefail\n" "python -m pip install -e .\n" "ruff check .\n" "pytest tests/unit\n",
        failures,
    )

    assert failures == []


def test_continue_on_error_is_rejected():
    audit = load_audit()
    failures: list[str] = []

    audit.check_workflow_fail_open(
        ".github/workflows/staging-release-gate.yml",
        "      continue-on-error: true\n",
        failures,
    )

    assert len(failures) == 1
    assert "fail-open" in failures[0]


def test_exact_release_workflow_is_governed():
    audit = load_audit()

    assert ".github/workflows/release.yml" in audit.GOVERNED_WORKFLOWS
    assert ".github/workflows/supabase-db-tests.yml" in audit.GOVERNED_WORKFLOWS
    assert all(
        marker in audit.REQUIRED_MARKERS[".github/workflows/release.yml"]
        for marker in ("mypy", "backup_verify.py", "final_health_check.py")
    )


def test_backup_verifier_is_real_and_fail_closed() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "scripts" / "backup_verify.py").read_text(encoding="utf-8")

    assert "mock://test" not in source
    assert 'status": "success"' not in source
    assert "pg_dump" in source
    assert "pg_restore" in source
    assert "database_snapshot" in source
    assert "migration/security verification failed" in source
