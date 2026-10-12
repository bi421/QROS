from __future__ import annotations

from datetime import datetime, timezone

from researchos.market_memory.decision_time_adapter import market_memory_to_decision_evidence_as_of
from researchos.market_memory.event_schema import EvidenceRecord, EvidenceStatus, MarketMemoryReport


def _record(name: str, end: str) -> EvidenceRecord:
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
        uncertainty={"provenance": {"dataset_version_bound": "canonical-v1"}},
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


def test_as_of_gate_accepts_only_records_whose_data_window_ends_by_cutoff() -> None:
    report = _report(
        _record("historical", "2024-12-31T00:00:00+00:00"),
        _record("future", "2025-06-01T00:00:00+00:00"),
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
        _record("historical", "2025-06-01T00:00:00+00:00"),
        date_range=("2021-01-01T00:00:00+00:00", "2025-06-01T00:00:00+00:00"),
    )
    assert market_memory_to_decision_evidence_as_of(
        report, decision_time=datetime(2025, 2, 1, tzinfo=timezone.utc)
    ) == []


def test_as_of_gate_requires_timezone_aware_decision_time() -> None:
    report = _report(_record("historical", "2024-12-31T00:00:00+00:00"))
    try:
        market_memory_to_decision_evidence_as_of(report, decision_time=datetime(2025, 2, 1))
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("naive decision_time must fail closed")
