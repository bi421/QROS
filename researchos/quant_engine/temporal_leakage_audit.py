"""Independent temporal split and feature-availability leakage audit.

A passing audit verifies timestamp boundaries for the supplied records only. It
cannot prove that upstream feature construction is free from hidden look-ahead.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol, TypeVar

from researchos.quant_engine.mathematical_falsification import AuditStatus, MathematicalAudit


class _TimedRecord(Protocol):
    @property
    def timestamp(self) -> datetime: ...


RecordT = TypeVar("RecordT", bound=_TimedRecord)


def audit_temporal_leakage(
    train: Sequence[RecordT],
    validation: Sequence[RecordT],
    test: Sequence[RecordT],
    *,
    label_end_getter: Callable[[RecordT], datetime | None],
    feature_available_at_getter: Callable[[RecordT], datetime | None] | None = None,
    tolerance_seconds: float = 0.0,
) -> MathematicalAudit:
    """Audit ordered partitions, label-window boundaries, and feature availability.

    Label windows are treated as half-open [event timestamp, label end). A
    training label must end strictly before validation starts; a validation
    label must end strictly before test starts. If feature availability is
    supplied, every feature timestamp must be no later than its event timestamp.
    """
    try:
        if tolerance_seconds < 0:
            raise ValueError("tolerance_seconds must be >= 0")
        partitions = (("train", train), ("validation", validation), ("test", test))
        for name, records in partitions:
            if not records:
                raise ValueError(f"{name} partition is empty; leakage status cannot be verified")
            timestamps = [record.timestamp for record in records]
            if any(not isinstance(ts, datetime) for ts in timestamps):
                raise ValueError(f"{name} contains a non-datetime event timestamp")
            if any(current <= previous for previous, current in zip(timestamps, timestamps[1:])):
                raise ValueError(f"{name} timestamps must be strictly increasing")

        train_start, train_end = train[0].timestamp, train[-1].timestamp
        validation_start, validation_end = validation[0].timestamp, validation[-1].timestamp
        test_start, test_end = test[0].timestamp, test[-1].timestamp
        if not train_end < validation_start:
            raise ValueError("partition order violation: train overlaps validation")
        if not validation_end < test_start:
            raise ValueError("partition order violation: validation overlaps test")
        if not train_start <= train_end < validation_start <= validation_end < test_start <= test_end:
            raise ValueError("partitions are not strictly chronological")

        issues: list[str] = []
        for name, records, boundary in (
            ("train", train, validation_start),
            ("validation", validation, test_start),
        ):
            for index, record in enumerate(records):
                label_end = label_end_getter(record)
                if label_end is None:
                    issues.append(f"{name}[{index}] has no realized label end")
                    continue
                if not isinstance(label_end, datetime):
                    issues.append(f"{name}[{index}] label end is not a datetime")
                    continue
                if label_end.tzinfo != record.timestamp.tzinfo:
                    issues.append(f"{name}[{index}] label/event timezone mismatch")
                    continue
                if (label_end - boundary).total_seconds() >= -tolerance_seconds:
                    issues.append(f"{name}[{index}] label reaches or crosses next partition boundary")

        if feature_available_at_getter is not None:
            for name, records in partitions:
                for index, record in enumerate(records):
                    available_at = feature_available_at_getter(record)
                    if available_at is None:
                        issues.append(f"{name}[{index}] has no feature-availability timestamp")
                    elif not isinstance(available_at, datetime):
                        issues.append(f"{name}[{index}] feature-availability timestamp is not a datetime")
                    elif available_at.tzinfo != record.timestamp.tzinfo:
                        issues.append(f"{name}[{index}] feature/event timezone mismatch")
                    elif available_at > record.timestamp:
                        issues.append(f"{name}[{index}] uses a feature unavailable at event time")
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        return MathematicalAudit(
            "temporal_leakage",
            AuditStatus.INVALID_INPUT,
            "temporal partition contract",
            None,
            None,
            None,
            tolerance_seconds,
            (),
            f"Cannot verify temporal leakage boundaries: {exc}",
        )

    if issues:
        return MathematicalAudit(
            "temporal_leakage",
            AuditStatus.FALSIFIED,
            "temporal boundaries",
            0.0,
            float(len(issues)),
            float(len(issues)),
            tolerance_seconds,
            (
                "event timestamps represent when the forecast could have been made",
                "label-end timestamps represent the final observation used by each outcome",
                "feature availability timestamps represent when each feature was actually knowable",
            ),
            "Temporal leakage contract violated: " + "; ".join(issues[:8]),
        )

    return MathematicalAudit(
        "temporal_leakage",
        AuditStatus.VERIFIED,
        "temporal boundaries",
        0.0,
        0.0,
        0.0,
        tolerance_seconds,
        (
            "event timestamps represent when the forecast could have been made",
            "label-end timestamps represent the final observation used by each outcome",
            "feature availability timestamps represent when each feature was actually knowable when supplied",
        ),
        "No boundary violation was found in the supplied partitions. This does not prove that upstream feature calculations or data provenance are free of look-ahead leakage.",
    )


__all__ = ["audit_temporal_leakage"]
