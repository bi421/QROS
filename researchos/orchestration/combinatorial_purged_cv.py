"""Combinatorial purged cross-validation with explicit purge/embargo audit trails.

Research-only. Each split stores exact row indices removed for label overlap and
embargo, the retained train/test indices, and fold metrics. ISO timestamps must be
strictly chronological and use a consistent timezone convention.
"""

from __future__ import annotations

import itertools
import math
from bisect import bisect_left
from datetime import datetime, timedelta
from statistics import mean, median
from typing import Any

from researchos.orchestration.logistic_probability import fit_evaluate_logistic


def _parse_time(value: Any, *, field: str, row_index: int) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"row {row_index}: {field} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"row {row_index}: invalid ISO-8601 {field}") from exc
    return parsed


def _time_id(row: dict[str, Any], index: int) -> str:
    event_id = row.get("event_id")
    return str(event_id) if event_id is not None else str(index)


def combinatorial_purged_cv_evaluate(
    rows: list[dict[str, Any]],
    *,
    n_groups: int = 6,
    n_test_groups: int = 2,
    embargo: timedelta = timedelta(0),
    min_train_rows: int = 100,
    l2: float = 1.0,
) -> dict[str, Any]:
    """Evaluate all test-group combinations and retain exact split membership.

    A candidate training event is purged if its [timestamp, label_end_timestamp]
    interval overlaps any test event interval. An otherwise eligible training event
    is embargoed when its start is after a test block's end and no later than
    test-block end + embargo. Embargo is time-based, not a row-count approximation.
    """
    if not rows:
        return {"status": "INSUFFICIENT_DATA", "splits": [], "n_events": 0}
    if isinstance(n_groups, bool) or not isinstance(n_groups, int) or n_groups < 3:
        raise ValueError("n_groups must be an integer >= 3")
    if (
        isinstance(n_test_groups, bool)
        or not isinstance(n_test_groups, int)
        or not 1 <= n_test_groups < n_groups
    ):
        raise ValueError("n_test_groups must be between 1 and n_groups-1")
    if not isinstance(embargo, timedelta) or embargo < timedelta(0):
        raise ValueError("embargo must be a nonnegative timedelta")
    if (
        isinstance(min_train_rows, bool)
        or not isinstance(min_train_rows, int)
        or min_train_rows < 20
    ):
        raise ValueError("min_train_rows must be an integer >= 20")
    if not math.isfinite(l2) or l2 < 0:
        raise ValueError("l2 must be finite and >= 0")

    starts = [
        _parse_time(row.get("timestamp"), field="timestamp", row_index=i)
        for i, row in enumerate(rows)
    ]
    ends = [
        _parse_time(row.get("label_end_timestamp"), field="label_end_timestamp", row_index=i)
        for i, row in enumerate(rows)
    ]
    awareness = {value.utcoffset() is not None for value in starts + ends}
    if len(awareness) > 1:
        raise ValueError("timestamps must use a consistent timezone convention")
    if any(starts[i] >= starts[i + 1] for i in range(len(starts) - 1)):
        raise ValueError(
            "event timestamps must be strictly increasing and unique; refusing to reorder"
        )
    if any(ends[i] < starts[i] for i in range(len(rows))):
        raise ValueError("label_end_timestamp must be >= timestamp")
    if len({_time_id(row, i) for i, row in enumerate(rows)}) != len(rows):
        raise ValueError("event_id values must be unique when supplied")

    n = len(rows)
    group_count = min(n_groups, n)
    if group_count != n_groups:
        raise ValueError("n_groups cannot exceed event count")
    groups = [
        list(range(group * n // n_groups, (group + 1) * n // n_groups)) for group in range(n_groups)
    ]
    split_combinations = list(itertools.combinations(range(n_groups), n_test_groups))
    splits: list[dict[str, Any]] = []
    for split_number, test_group_ids in enumerate(split_combinations, start=1):
        test_indices = sorted(index for group_id in test_group_ids for index in groups[group_id])
        test_set = set(test_indices)
        test_intervals = sorted((starts[i], ends[i]) for i in test_indices)
        merged_intervals: list[tuple[datetime, datetime]] = []
        for interval_start, interval_end in test_intervals:
            if merged_intervals and interval_start <= merged_intervals[-1][1]:
                merged_intervals[-1] = (
                    merged_intervals[-1][0],
                    max(merged_intervals[-1][1], interval_end),
                )
            else:
                merged_intervals.append((interval_start, interval_end))
        merged_starts = [interval[0] for interval in merged_intervals]
        merged_ends = [interval[1] for interval in merged_intervals]
        test_block_ends = [max(ends[i] for i in groups[group_id]) for group_id in test_group_ids]
        candidate_train = [i for i in range(n) if i not in test_set]
        purged_indices: list[int] = []
        embargo_indices: list[int] = []
        train_indices: list[int] = []
        purge_reasons: dict[str, list[int]] = {}
        embargo_reasons: dict[str, list[int]] = {}

        for index in candidate_train:
            interval_position = bisect_left(merged_ends, starts[index])
            has_overlap = (
                interval_position < len(merged_intervals)
                and merged_starts[interval_position] <= ends[index]
            )
            overlaps = []
            if has_overlap:
                overlaps = [
                    test_i
                    for test_i in test_indices
                    if starts[index] <= ends[test_i] and ends[index] >= starts[test_i]
                ]
            if overlaps:
                purged_indices.append(index)
                purge_reasons[str(index)] = overlaps
                continue
            embargoed_by = [
                group_id
                for group_id, block_end in zip(test_group_ids, test_block_ends, strict=True)
                if block_end < starts[index] <= block_end + embargo
            ]
            if embargoed_by:
                embargo_indices.append(index)
                embargo_reasons[str(index)] = embargoed_by
                continue
            train_indices.append(index)

        split: dict[str, Any] = {
            "split": split_number,
            "test_group_ids_zero_based": list(test_group_ids),
            "test_indices_zero_based": test_indices,
            "test_event_ids": [_time_id(rows[i], i) for i in test_indices],
            "candidate_train_n": len(candidate_train),
            "train_indices_zero_based": train_indices,
            "train_event_ids": [_time_id(rows[i], i) for i in train_indices],
            "purged_indices_zero_based": purged_indices,
            "purged_event_ids": [_time_id(rows[i], i) for i in purged_indices],
            "purge_reason_test_indices_by_train_index": purge_reasons,
            "embargo_indices_zero_based": embargo_indices,
            "embargo_event_ids": [_time_id(rows[i], i) for i in embargo_indices],
            "embargo_reason_test_group_ids_by_train_index": embargo_reasons,
            "train_n": len(train_indices),
            "test_n": len(test_indices),
            "purged_n": len(purged_indices),
            "embargo_n": len(embargo_indices),
            "embargo_seconds": int(embargo.total_seconds()),
            "test_start": starts[test_indices[0]].isoformat(),
            "test_end": max(ends[i] for i in test_indices).isoformat(),
        }
        if len(train_indices) < min_train_rows:
            split.update({"status": "INSUFFICIENT_TRAIN_AFTER_PURGE_EMBARGO", "metrics": None})
        else:
            result = fit_evaluate_logistic(
                [rows[i] for i in train_indices],
                [rows[i] for i in test_indices],
                l2=l2,
            )
            split.update(
                {
                    "status": result.get("status", "UNKNOWN"),
                    "metrics": result.get("holdout_metrics"),
                    "baseline_metrics": result.get("holdout_train_prevalence_baseline_metrics"),
                }
            )
        splits.append(split)

    valid = [s for s in splits if s.get("metrics")]
    summary: dict[str, Any] = {}
    for metric in ("log_loss", "brier_score", "expected_calibration_error_10_bins"):
        values = [float(s["metrics"][metric]) for s in valid]
        baseline = [
            float(s["baseline_metrics"][metric]) for s in valid if s.get("baseline_metrics")
        ]
        summary[metric] = {
            "n_splits": len(values),
            "mean": mean(values) if values else None,
            "median": median(values) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "baseline_mean": mean(baseline) if baseline else None,
            "values": values,
        }
    purge_counts = [s["purged_n"] for s in splits]
    embargo_counts = [s["embargo_n"] for s in splits]
    return {
        "status": "COMPLETED" if valid else "INSUFFICIENT_VALID_SPLITS",
        "method": "Combinatorial purged CV; interval-overlap purge plus time-based embargo",
        "n_events": n,
        "n_groups": n_groups,
        "n_test_groups": n_test_groups,
        "requested_split_count": len(split_combinations),
        "valid_split_count": len(valid),
        "embargo_seconds": int(embargo.total_seconds()),
        "purge_policy": "remove train event when [event start, label end] overlaps any test event interval; boundary contact counts as overlap",
        "embargo_policy": "remove otherwise eligible train events starting after a test block end and at or before end + embargo",
        "split_membership_saved": True,
        "purged_n_distribution": {
            "min": min(purge_counts),
            "max": max(purge_counts),
            "total_across_splits": sum(purge_counts),
        },
        "embargo_n_distribution": {
            "min": min(embargo_counts),
            "max": max(embargo_counts),
            "total_across_splits": sum(embargo_counts),
        },
        "metric_distribution": summary,
        "splits": splits,
        "warning": "Split scores are dependent and are not independent replications. This reports CPCV-style combinatorial test splits, not stitched CPCV backtest paths or proof of economic edge. Evaluate costs and untouched final holdout separately.",
    }


__all__ = ["combinatorial_purged_cv_evaluate"]
