from pathlib import Path

from scripts.check_migration_drift import audit, logical_name


def test_logical_name_strips_timestamp_and_sql_suffix():
    assert logical_name("20261005021400_billing_event_ordering.sql") == "billing_event_ordering"
    assert logical_name("billing_event_ordering") == "billing_event_ordering"


def test_matching_logical_name_reports_version_drift(tmp_path: Path):
    (tmp_path / "20261005021400_billing_event_ordering.sql").write_text("select 1;", encoding="utf-8")
    findings = audit(
        tmp_path,
        [{"version": "20261005022000", "name": "20261005021400_billing_event_ordering"}],
    )
    assert len(findings) == 1
    assert findings[0].startswith("VERSION_MISMATCH_REQUIRES_PROVENANCE_REVIEW")


def test_missing_database_row_is_not_auto_classified_as_unapplied(tmp_path: Path):
    (tmp_path / "20261005021400_billing_event_ordering.sql").write_text("select 1;", encoding="utf-8")
    findings = audit(tmp_path, [])
    assert findings == [
        "REPO_ONLY_REQUIRES_SCHEMA_REVIEW: 20261005021400_billing_event_ordering.sql"
    ]


def test_duplicate_logical_names_are_reported(tmp_path: Path):
    (tmp_path / "20261005021400_billing_event_ordering.sql").write_text("select 1;", encoding="utf-8")
    (tmp_path / "20261005022000_billing_event_ordering.sql").write_text("select 2;", encoding="utf-8")
    findings = audit(tmp_path, [])
    assert any(item.startswith("DUPLICATE_REPO_LOGICAL_NAME") for item in findings)
