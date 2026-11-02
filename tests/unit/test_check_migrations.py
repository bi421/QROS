from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_migrations.py"
SPEC = spec_from_file_location("qros_check_migrations", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
check_migrations = module_from_spec(SPEC)
SPEC.loader.exec_module(check_migrations)

REQUIRED = (
    "202609200000_r3_result_client_grants_deny.sql",
    "202609200003_r3_security_boundary_assertions_v2.sql",
)


def _seed_required_migrations(path: Path) -> None:
    for name in REQUIRED:
        (path / name).write_text("-- fixture\n", encoding="utf-8")


def test_accepts_legacy_and_modern_timestamp_widths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_required_migrations(tmp_path)
    (tmp_path / "20261102000100_default_privileges_hardening.sql").write_text(
        "select 1;\n", encoding="utf-8"
    )
    (tmp_path / "20261102000101_default_privileges_followup.sql").write_text(
        "select 1;\n", encoding="utf-8"
    )
    monkeypatch.setattr(check_migrations, "MIGRATIONS", tmp_path)

    check_migrations.main()
    assert "migration integrity OK: 4 files" in capsys.readouterr().out


def test_rejects_invalid_thirteen_digit_timestamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_required_migrations(tmp_path)
    (tmp_path / "2026110200010_invalid_width.sql").write_text(
        "select 1;\n", encoding="utf-8"
    )
    monkeypatch.setattr(check_migrations, "MIGRATIONS", tmp_path)

    with pytest.raises(SystemExit, match="invalid migration filename"):
        check_migrations.main()


def test_rejects_duplicate_exact_timestamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_required_migrations(tmp_path)
    (tmp_path / "20261102000100_default_privileges_hardening.sql").write_text(
        "select 1;\n", encoding="utf-8"
    )
    (tmp_path / "20261102000100_duplicate_version.sql").write_text(
        "select 2;\n", encoding="utf-8"
    )
    monkeypatch.setattr(check_migrations, "MIGRATIONS", tmp_path)

    with pytest.raises(
        SystemExit, match="duplicate migration timestamp: 20261102000100"
    ):
        check_migrations.main()
