from scripts.audit_fast_three_state_triple_barrier import causal_atr, make_labels, score


def test_atr_is_causal_and_uses_prior_close_for_true_range():
    high = [11.0, 12.0, 13.0, 14.0]
    low = [9.0, 10.0, 11.0, 12.0]
    close = [10.0, 11.0, 12.0, 13.0]
    atr = causal_atr(high, low, close, 2)
    assert atr[0] is None
    assert atr[1] == 2.0
    assert atr[2] == 2.0
    assert atr[3] == 2.0


def test_barrier_label_uses_future_bars_and_excludes_double_touch():
    opens = [100.0, 100.0, 100.0, 100.0]
    highs = [100.5, 102.0, 100.5, 100.5]
    lows = [99.5, 98.0, 99.5, 99.5]
    closes = [100.0, 100.0, 100.0, 100.0]
    labels, ends = make_labels(opens, highs, lows, closes, [1.0] * 4, 2, 1.0, 1.0)
    assert labels[0] is None
    assert ends[0] == 1


def test_score_counts_all_three_classes_and_baseline():
    result = score([("UP", "UP"), ("DOWN", "RANGE"), ("RANGE", "RANGE")])
    assert result["n"] == 3
    assert result["accuracy"] == 2 / 3
    assert result["confusion_matrix_actual_rows_predicted_columns"]["DOWN"]["RANGE"] == 1
