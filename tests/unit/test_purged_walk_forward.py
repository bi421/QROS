from datetime import datetime, timedelta

from researchos.orchestration.purged_walk_forward import purged_walk_forward_evaluate


def _rows(n=300):
    start = datetime(2024, 1, 1)
    rows = []
    for i in range(n):
        ts = start + timedelta(minutes=15 * i)
        end = ts + timedelta(minutes=15 * 3)
        z = (i % 11) / 5.0
        aligned = float(i % 2)
        rows.append(
            {
                "timestamp": ts.isoformat(),
                "label_end_timestamp": end.isoformat(),
                "z_speed": z,
                "body_ratio": (i % 7) / 7.0,
                "upper_wick_ratio": (i % 5) / 5.0,
                "lower_wick_ratio": ((i + 2) % 5) / 5.0,
                "h1_aligned": aligned,
                "label": int(z + aligned * 0.7 > 1.0),
            }
        )
    return rows


def test_walk_forward_is_expanding_and_purges_overlapping_labels():
    result = purged_walk_forward_evaluate(_rows(), n_splits=4, min_train_rows=40)
    assert result["status"] == "COMPLETED"
    assert result["valid_folds"] == 4
    assert all(fold["purged_n"] >= 1 for fold in result["folds"])
    assert all(fold["train_n"] >= 40 for fold in result["folds"])
    assert result["mean_metrics"]["log_loss"]["mean"] >= 0


def test_walk_forward_rejects_duplicate_event_timestamps():
    rows = _rows(80)
    rows[1]["timestamp"] = rows[0]["timestamp"]
    result = None
    try:
        result = purged_walk_forward_evaluate(rows, n_splits=2, min_train_rows=20)
    except ValueError as exc:
        assert "unique" in str(exc)
    assert result is None


def test_walk_forward_rejects_out_of_order_source_rows_without_sorting():
    rows = _rows(80)
    rows[10], rows[11] = rows[11], rows[10]
    try:
        purged_walk_forward_evaluate(rows, n_splits=2, min_train_rows=20)
    except ValueError as exc:
        assert "refusing to reorder" in str(exc)
    else:
        raise AssertionError("out-of-order source rows must be rejected")
