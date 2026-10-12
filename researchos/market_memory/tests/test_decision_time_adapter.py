from __future__ import annotations

from datetime import datetime, timezone

from researchos.market_memory.decision_time_adapter import market_memory_to_decision_evidence_as_of
from researchos.market_memory.event_schema import EvidenceRecord, EvidenceStatus, MarketMemoryReport


def _record(
    name: str,
    end: str,
    maturity: str = "2025-01-20T00:00:00+00:00",
) -> EvidenceRecord:
    return EvidenceRecord(
        finding_id=f"EVIDENCE|{name}",
        finding_name=name,
        dataset_id="xauusd-d1",
        dataset_version="canonical-v1",
        event_definition="SMA20/100 crossover",
        condition_definition="{'direction':'bullish'}",
        sample_size=250,
        time_range=("2021-01-01T00:00:00+00:00", end),
        computation_method="forward_return_analysis",
        code_module="test",
        statistical_method="wilson",
        result={"raw_probability": 0.7},
        uncertainty={
            "provenance": {
                "dataset_version_bound": "canonical-v1",
                "outcome_maturity_at": maturity,
            }
        },
        status=EvidenceStatus.VALIDATED.value,
    )


def _report(
    *records: EvidenceRecord,
    generated_at: str = "2025-01-02T00:00:00+00:00",
    date_range: tuple[str, str] = (
        "2021-01-01T00:00:00+00:00",
        "2024-12-31T00:00:00+00:00",
    ),
) -> MarketMemoryReport:
    return MarketMemoryReport(
        report_id="MMR|XAUUSD|D1|test",
        asset="XAUUSD",
        timeframe="D1",
        event_type="sma_crossover",
        generated_at=generated_at,
        date_range=date_range,
        evidence_records=list(records),
        overall_status=EvidenceStatus.VALIDATED.value,
    )


def test_as_of_gate_accepts_only_records_whose_outcomes_matured_by_cutoff() -> None:
    report = _report(
        _record("historical", "2024-12-31T00:00:00+00:00"),
        _record("future", "2025-06-01T00:00:00+00:00", "2025-06-21T00:00:00+00:00"),
    )
    items = market_memory_to_decision_evidence_as_of(
        report, decision_time=datetime(2025, 2, 1, tzinfo=timezone.utc)
    )
    assert [item.source_id for item in items] == ["EVIDENCE|historical"]


def test_as_of_gate_rejects_report_generated_after_decision_time() -> None:
    report = _report(
        _record("historical", "2024-12-31T00:00:00+00:00"),
        generated_at="2025-01-02T00:00:00+00:00",
        date_range=("2021-01-01T00:00:00+00:00", "2024-12-31T00:00:00+00:00"),
    )
    assert market_memory_to_decision_evidence_as_of(
        report, decision_time=datetime(2025, 1, 1, tzinfo=timezone.utc)
    ) == []


def test_as_of_gate_rejects_future_report_data_range() -> None:
    report = _report(
        _record("historical", "2025-06-01T00:00:00+00:00", "2025-06-21T00:00:00+00:00"),
        date_range=("2021-01-01T00:00:00+00:00", "2025-06-01T00:00:00+00:00"),
    )
    assert market_memory_to_decision_evidence_as_of(
        report, decision_time=datetime(2025, 2, 1, tzinfo=timezone.utc)
    ) == []


def test_as_of_gate_treats_date_only_upper_bound_as_end_of_day() -> None:
    report = _report(
        _record("historical", "2024-12-31", "2025-01-20"),
        generated_at="2024-12-31T08:00:00+00:00",
        date_range=("2021-01-01", "2024-12-31"),
    )
    assert market_memory_to_decision_evidence_as_of(
        report, decision_time=datetime(2024, 12, 31, 12, tzinfo=timezone.utc)
    ) == []


def test_as_of_gate_rejects_missing_outcome_maturity_provenance() -> None:
    record = _record("missing-maturity", "2024-12-31T00:00:00+00:00")
    record = EvidenceRecord(
        finding_id=record.finding_id,
        finding_name=record.finding_name,
        dataset_id=record.dataset_id,
        dataset_version=record.dataset_version,
        event_definition=record.event_definition,
        condition_definition=record.condition_definition,
        sample_size=record.sample_size,
        time_range=record.time_range,
        computation_method=record.computation_method,
        code_module=record.code_module,
        statistical_method=record.statistical_method,
        result=record.result,
        uncertainty={"provenance": {"dataset_version_bound": "canonical-v1"}},
        status=record.status,
    )
    assert market_memory_to_decision_evidence_as_of(
        _report(record), decision_time=datetime(2025, 2, 1, tzinfo=timezone.utc)
    ) == []


def test_as_of_gate_requires_timezone_aware_decision_time() -> None:
    report = _report(_record("historical", "2024-12-31T00:00:00+00:00"))
    try:
        market_memory_to_decision_evidence_as_of(report, decision_time=datetime(2025, 2, 1))
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("naive decision_time must fail closed")
