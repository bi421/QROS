"""Decision-time gate for Market Memory evidence.

This is an additive, fail-closed bridge. The legacy adapter remains available for
exploratory/offline analysis; decision-time consumers should use this function.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timezone

from researchos.decision_engine.contracts import DecisionEvidenceItem
from researchos.market_memory.decision_adapter import market_memory_to_decision_evidence
from researchos.market_memory.event_schema import MarketMemoryReport


def _parse_timestamp(
    value: str,
    *,
    field_name: str,
    end_of_day: bool = False,
) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} is not an ISO-8601 timestamp") from exc
    # A date-only upper bound represents the entire calendar day, not midnight
    # at its start. This prevents a same-day partial window from passing early.
    if len(value.strip()) == 10 and end_of_day:
        parsed = datetime.combine(parsed.date(), time.max, tzinfo=timezone.utc)
    elif parsed.tzinfo is None or parsed.utcoffset() is None:
        # Never inherit the host machine's local timezone.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def market_memory_to_decision_evidence_as_of(
    report: MarketMemoryReport,
    *,
    decision_time: datetime,
    directional_only: bool = True,
) -> list[DecisionEvidenceItem]:
    """Return validated Market Memory evidence with matured outcomes by cutoff.

    A report generated after the decision time is rejected in full. Missing or
    future report bounds also fail closed. Each finding must declare an explicit
    provenance outcome_maturity_at timestamp, which must be at or before the
    decision time and no earlier than its evidence window end. This avoids
    treating event timestamps as proof that forward outcomes were already known.
    The gate is conservative, but does not replace immutable dataset and method
    provenance validation by the caller.
    """
    if decision_time.tzinfo is None or decision_time.utcoffset() is None:
        raise ValueError("decision_time must be timezone-aware")
    cutoff = decision_time.astimezone(timezone.utc)

    generated_at = _parse_timestamp(report.generated_at, field_name="report.generated_at")
    if generated_at > cutoff:
        return []

    if len(report.date_range) != 2:
        return []
    try:
        data_start = _parse_timestamp(report.date_range[0], field_name="report.date_range.start")
        data_end = _parse_timestamp(
            report.date_range[1],
            field_name="report.date_range.end",
            end_of_day=True,
        )
    except ValueError:
        return []
    if data_start > data_end or data_end > cutoff:
        return []

    eligible_records = []
    for record in report.evidence_records:
        if len(record.time_range) != 2:
            continue
        try:
            record_start = _parse_timestamp(
                record.time_range[0],
                field_name="evidence.time_range.start",
            )
            record_end = _parse_timestamp(
                record.time_range[1],
                field_name="evidence.time_range.end",
                end_of_day=True,
            )
            provenance = record.uncertainty.get("provenance")
            if not isinstance(provenance, dict):
                continue
            maturity = _parse_timestamp(
                provenance.get("outcome_maturity_at"),
                field_name="evidence.provenance.outcome_maturity_at",
                end_of_day=True,
            )
        except (AttributeError, TypeError, ValueError):
            continue
        if record_start <= record_end <= maturity <= cutoff:
            eligible_records.append(record)

    bounded_report = replace(report, evidence_records=eligible_records)
    return market_memory_to_decision_evidence(
        bounded_report,
        directional_only=directional_only,
    )


__all__ = ["market_memory_to_decision_evidence_as_of"]
