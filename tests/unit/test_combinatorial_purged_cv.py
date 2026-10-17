from datetime import datetime, timedelta

import pytest

from researchos.orchestration.combinatorial_purged_cv import combinatorial_purged_cv_evaluate


def _rows(n=240):
    start = datetime(2024, 1, 1)
    rows = []
    for i in range(n):
        ts = start + timedelta(minutes=15 * i)
        z = (i % 11) / 5.0
        aligned = float(i % 2)
        rows.append(
            {
                "event_id": f"evt-{i:04d}",
                "timestamp": ts.isoformat(),
                "label_end_timestamp": (ts + timedelta(minutes=45)).isoformat(),
                "z_speed": z,
                "body_ratio": (i % 7) / 7.0,
                "upper_wick_ratio": (i % 5) / 5.0,
                "lower_wick_ratio": ((i + 2) % 5) / 5.0,
                "h1_aligned": aligned,
                "label": int(z + aligned * 0.7 > 1.0),
            }
        )
    return rows


def test_cpcv_evaluates_all_combinations_and_persists_membership():
    rows = _rows()
    result = combinatorial_purged_cv_evaluate(rows, n_groups=6, n_test_groups=2, min_train_rows=40)
    assert result["status"] == "COMPLETED"
    assert result["requested_split_count"] == 15
    assert result["valid_split_count"] == 15
    for split in result["splits"]:
        assert split["test_indices_zero_based"]
        assert split["train_indices_zero_based"]
        assert split["purged_indices_zero_based"]
        assert set(split["train_indices_zero_based"]).isdisjoint(split["test_indices_zero_based"])
        assert set(split["purged_indices_zero_based"]).isdisjoint(split["test_indices_zero_based"])
        assert split["purged_n"] == len(split["purged_event_ids"])
        for train_i in split["train_indices_zero_based"]:
            assert not any(
                rows[train_i]["timestamp"] <= rows[test_i]["label_end_timestamp"]
                and rows[train_i]["label_end_timestamp"] >= rows[test_i]["timestamp"]
                for test_i in split["test_indices_zero_based"]
            )
        for train_i in split["purged_indices_zero_based"]:
            expected = [
                test_i
                for test_i in split["test_indices_zero_based"]
                if rows[train_i]["timestamp"] <= rows[test_i]["label_end_timestamp"]
                and rows[train_i]["label_end_timestamp"] >= rows[test_i]["timestamp"]
            ]
            assert split["purge_reason_test_indices_by_train_index"][str(train_i)] == expected
    assert result["metric_distribution"]["log_loss"]["n_splits"] == 15


def test_cpcv_embargo_reports_exact_removed_rows_and_reasons():
    result = combinatorial_purged_cv_evaluate(
        _rows(180),
        n_groups=6,
        n_test_groups=1,
        embargo=timedelta(minutes=60),
        min_train_rows=20,
    )
    assert result["status"] == "COMPLETED"
    assert result["embargo_n_distribution"]["total_across_splits"] > 0
    for split in result["splits"]:
        assert split["embargo_n"] == len(split["embargo_indices_zero_based"])
        assert split["embargo_n"] == len(split["embargo_reason_test_group_ids_by_train_index"])
        assert set(split["embargo_indices_zero_based"]).isdisjoint(
            split["train_indices_zero_based"]
        )


def test_cpcv_rejects_unsorted_rows_and_bad_label_intervals():
    rows = _rows(80)
    rows[10], rows[11] = rows[11], rows[10]
    with pytest.raises(ValueError, match="refusing to reorder"):
        combinatorial_purged_cv_evaluate(rows, n_groups=4, n_test_groups=1, min_train_rows=20)

    rows = _rows(80)
    rows[20]["label_end_timestamp"] = (
        datetime.fromisoformat(rows[20]["timestamp"]) - timedelta(minutes=1)
    ).isoformat()
    with pytest.raises(ValueError, match="label_end_timestamp must be >="):
        combinatorial_purged_cv_evaluate(rows, n_groups=4, n_test_groups=1, min_train_rows=20)


def test_cpcv_rejects_duplicate_event_ids():
    rows = _rows(80)
    rows[1]["event_id"] = rows[0]["event_id"]
    with pytest.raises(ValueError, match="event_id values must be unique"):
        combinatorial_purged_cv_evaluate(rows, n_groups=4, n_test_groups=1, min_train_rows=20)
