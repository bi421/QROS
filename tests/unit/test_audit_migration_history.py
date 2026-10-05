from scripts.audit_migration_history import audit


def test_audit_separates_exact_and_historical_alias_matches() -> None:
    result = audit(
        ["20260101000000_first", "20260102000000_second", "20260103000000_third"],
        ["20260101000000_first", "historical_second", "unrelated"],
        {"20260102000000_second": "historical_second"},
    )

    assert result["canonical_count"] == 3
    assert result["remote_count"] == 3
    assert result["exact_matches"] == ["20260101000000_first"]
    assert result["historical_alias_matches"] == [
        {
            "canonical": "20260102000000_second",
            "remote": "historical_second",
        }
    ]
    assert result["missing_canonical_names"] == ["20260103000000_third"]
    assert result["history_parity"] is False
    assert result["schema_equivalence"] == "NOT_EVALUATED"
    assert result["mutation_performed"] is False


def test_duplicate_history_rows_are_reported() -> None:
    result = audit(
        ["20260101000000_first"],
        ["20260101000000_first", "20260101000000_first"],
        {},
    )

    assert result["duplicate_remote_names"] == ["20260101000000_first"]
    assert result["history_parity"] is True
