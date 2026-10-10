"""Regression tests for independent temporal leakage audit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from researchos.quant_engine.mathematical_falsification import AuditStatus
from researchos.quant_engine.temporal_leakage_audit import audit_temporal_leakage


@dataclass(frozen=True)
class Record:
    timestamp: datetime
    label_end: datetime | None
    feature_available_at: datetime | None


def _record(day: int, label_end_day: int, feature_day: int | None = None) -> Record:
    timestamp = datetime(2025, 1, day, tzinfo=timezone.utc)
    return Record(
        timestamp=timestamp,
        label_end=datetime(2025, 1, label_end_day, tzinfo=timezone.utc),
        feature_available_at=datetime(2025, 1, feature_day or day, tzinfo=timezone.utc),
    )


def _audit(train, validation, test):
    return audit_temporal_leakage(
        train, validation, test,
        label_end_getter=lambda record: record.label_end,
        feature_available_at_getter=lambda record: record.feature_available_at,
    )


def test_temporal_leakage_audit_verifies_clean_partitions() -> None:
    train = [_record(1, 2), _record(2, 3)]
    validation = [_record(5, 6), _record(6, 7)]
    test = [_record(9, 10), _record(10, 11)]

    result = _audit(train, validation, test)

    assert result.status is AuditStatus.VERIFIED


def test_temporal_leakage_audit_falsifies_train_label_crossing_validation() -> None:
    train = [_record(1, 5), _record(2, 3)]
    validation = [_record(5, 6)]
    test = [_record(9, 10)]

    result = _audit(train, validation, test)

    assert result.status is AuditStatus.FALSIFIED
    assert "train[0] label reaches or crosses" in result.explanation


def test_temporal_leakage_audit_falsifies_future_feature() -> None:
    train = [_record(1, 2, feature_day=2), _record(2, 3)]
    validation = [_record(5, 6)]
    test = [_record(9, 10)]

    result = _audit(train, validation, test)

    assert result.status is AuditStatus.FALSIFIED
    assert "feature unavailable at event time" in result.explanation


def test_temporal_leakage_audit_fails_closed_on_missing_partition() -> None:
    result = _audit([_record(1, 2)], [], [_record(9, 10)])

    assert result.status is AuditStatus.INVALID_INPUT
    assert "partition is empty" in result.explanation


def test_temporal_leakage_audit_fails_closed_on_missing_label_end() -> None:
    missing = Record(datetime(2025, 1, 1, tzinfo=timezone.utc), None, datetime(2025, 1, 1, tzinfo=timezone.utc))
    result = _audit(
        [missing],
        [_record(5, 6)],
        [_record(9, 10)],
    )

    assert result.status is AuditStatus.FALSIFIED
    assert "no realized label end" in result.explanation


def test_temporal_leakage_audit_fails_closed_on_unordered_partition() -> None:
    train = [_record(2, 3), _record(1, 2)]
    result = _audit(train, [_record(5, 6)], [_record(9, 10)])

    assert result.status is AuditStatus.INVALID_INPUT
    assert "strictly increasing" in result.explanation



def test_temporal_leakage_audit_falsifies_label_ending_before_event() -> None:
    invalid = Record(
        datetime(2025, 1, 2, tzinfo=timezone.utc),
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        datetime(2025, 1, 2, tzinfo=timezone.utc),
    )
    result = _audit(
        [invalid],
        [_record(5, 6)],
        [_record(9, 10)],
    )

    assert result.status is AuditStatus.FALSIFIED
    assert "label ends before its event timestamp" in result.explanation


def test_temporal_leakage_audit_is_inconclusive_without_feature_provenance() -> None:
    train = [_record(1, 2), _record(2, 3)]
    validation = [_record(5, 6)]
    test = [_record(9, 10)]

    result = audit_temporal_leakage(
        train,
        validation,
        test,
        label_end_getter=lambda record: record.label_end,
    )

    assert result.status is AuditStatus.INCONCLUSIVE
    assert "Feature-availability timestamps were not supplied" in result.explanation
