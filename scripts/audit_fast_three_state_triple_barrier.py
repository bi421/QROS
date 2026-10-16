"""Offline, chronological evaluation of FastThreeState against ATR triple-barrier labels.

Research diagnostic only: no trading orders, parameter tuning, or profitability claim.
"""

from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from researchos.orchestration.fast_three_state import FastThreeState

STATES = ("DOWN", "RANGE", "UP")


def causal_atr(high, low, close, period):
    if period < 1:
        raise ValueError("ATR period must be positive")
    tr = []
    for i, (h, low_value, c) in enumerate(zip(high, low, close)):
        if not all(math.isfinite(v) for v in (h, low_value, c)) or h < low_value:
            raise ValueError("invalid OHLC values")
        tr.append(h - low_value if i == 0 else max(h - low_value, abs(h - close[i - 1]), abs(low_value - close[i - 1])))
    result = [None] * len(tr)
    if len(tr) >= period:
        value = sum(tr[:period]) / period
        result[period - 1] = value
        for i in range(period, len(tr)):
            value = ((period - 1) * value + tr[i]) / period
            result[i] = value
    return result


def make_labels(opens, highs, lows, closes, atr, horizon, upper_atr, lower_atr):
    n = len(closes)
    if not all(len(x) == n for x in (opens, highs, lows, atr)):
        raise ValueError("OHLC and ATR arrays must have equal lengths")
    if horizon < 1 or upper_atr <= 0 or lower_atr <= 0:
        raise ValueError("horizon and ATR multipliers must be positive")
    labels = [None] * n
    ends = [None] * n
    for i in range(n):
        if atr[i] is None or not math.isfinite(atr[i]) or atr[i] <= 0 or i + horizon >= n:
            continue
        up = closes[i] + upper_atr * atr[i]
        down = closes[i] - lower_atr * atr[i]
        ends[i] = i + horizon
        for j in range(i + 1, i + horizon + 1):
            if opens[j] >= up:
                labels[i] = "UP"
                ends[i] = j
                break
            if opens[j] <= down:
                labels[i] = "DOWN"
                ends[i] = j
                break
            hit_up = highs[j] >= up
            hit_down = lows[j] <= down
            if hit_up and hit_down:
                labels[i] = None
                ends[i] = j
                break
            if hit_up:
                labels[i] = "UP"
                ends[i] = j
                break
            if hit_down:
                labels[i] = "DOWN"
                ends[i] = j
                break
            if j == i + horizon:
                labels[i] = "RANGE"
    return labels, ends


def score(rows):
    matrix = {a: {p: 0 for p in STATES} for a in STATES}
    for actual, pred in rows:
        matrix[actual][pred] += 1
    pc = {}
    for state in STATES:
        tp = matrix[state][state]
        support = sum(matrix[state].values())
        predicted = sum(matrix[a][state] for a in STATES)
        pc[state] = {
            "support": support,
            "precision": tp / predicted if predicted else None,
            "recall": tp / support if support else None,
        }
    total = len(rows)
    correct = sum(matrix[s][s] for s in STATES)
    supports = {s: sum(matrix[s].values()) for s in STATES}
    recalls = [pc[s]["recall"] for s in STATES if supports[s] > 0]
    return {
        "n": total,
        "accuracy": correct / total if total else None,
        "majority_class_baseline_accuracy": max(supports.values()) / total if total else None,
        "always_range_baseline_accuracy": supports["RANGE"] / total if total else None,
        "balanced_accuracy": sum(recalls) / len(recalls) if recalls else None,
        "confusion_matrix_actual_rows_predicted_columns": matrix,
        "per_class": pc,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv_path", type=Path)
    for name, default in (
        ("date-column", "Date"),
        ("time-column", "Time"),
        ("open-column", "Open"),
        ("high-column", "High"),
        ("low-column", "Low"),
        ("close-column", "Close"),
    ):
        p.add_argument("--" + name, default=default)
    p.add_argument("--atr-period", type=int, default=14)
    p.add_argument("--horizon", type=int, default=16)
    p.add_argument("--upper-atr", type=float, default=1.0)
    p.add_argument("--lower-atr", type=float, default=1.0)
    p.add_argument("--lookback", type=int, default=32)
    p.add_argument("--efficiency-threshold", type=float, default=0.35)
    p.add_argument("--min-move-bps", type=float, default=5.0)
    args = p.parse_args()
    digest = hashlib.sha256(args.csv_path.read_bytes()).hexdigest()
    with args.csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        raise ValueError("CSV contains no rows")
    keys = rows[0].keys()

    def key_for(wanted):
        match = next((k for k in keys if k.strip().lower() == wanted.lower()), None)
        if match is None:
            raise ValueError(f"missing CSV column: {wanted}")
        return match

    dk, tk = key_for(args.date_column), key_for(args.time_column)
    ok, hk, lk, ck = (
        key_for(x) for x in (args.open_column, args.high_column, args.low_column, args.close_column)
    )
    stamps = [str(r[dk]) + (" " + str(r[tk]) if tk != dk else "") for r in rows]
    anomalies = []

    def parse_stamp(value):
        for fmt in (
            "%Y.%m.%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y.%m.%d %H:%M",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass
        return None

    parsed = [parse_stamp(s) for s in stamps]
    for i in range(1, len(parsed)):
        if parsed[i] is not None and parsed[i - 1] is not None and parsed[i] < parsed[i - 1]:
            anomalies.append({"row_index": i, "previous": stamps[i - 1], "current": stamps[i]})
    opens = [float(r[ok]) for r in rows]
    highs = [float(r[hk]) for r in rows]
    lows = [float(r[lk]) for r in rows]
    closes = [float(r[ck]) for r in rows]
    atr = causal_atr(highs, lows, closes, args.atr_period)
    labels, ends = make_labels(
        opens, highs, lows, closes, atr, args.horizon, args.upper_atr, args.lower_atr
    )
    engine = FastThreeState(
        lookback=args.lookback,
        efficiency_threshold=args.efficiency_threshold,
        min_move_bps=args.min_move_bps,
    )
    predictions = [engine.update(c) for c in closes]
    pred_names = {1: "UP", -1: "DOWN", 0: "RANGE"}
    n = len(rows)
    train_stop = int(n * 0.70)
    val_stop = int(n * 0.85)
    folds = {}
    for name, start, stop in (
        ("train", 0, train_stop),
        ("validation", train_stop, val_stop),
        ("holdout", val_stop, n),
    ):
        pairs = []
        purged = 0
        excluded = 0
        for i in range(start, stop):
            if labels[i] is None:
                excluded += 1
                continue
            if ends[i] is not None and ends[i] >= stop and stop < n:
                purged += 1
                continue
            pairs.append((labels[i], pred_names[predictions[i]]))
        folds[name] = {
            "start_index": start,
            "stop_index_exclusive": stop,
            "n": len(pairs),
            "purged_cross_boundary_events": purged,
            "excluded_ambiguous_or_unavailable": excluded,
            "metrics": score(pairs),
        }
    label_counts = {s: sum(x == s for x in labels) for s in STATES}
    prediction_counts = {s: sum(pred_names[x] == s for x in predictions) for s in STATES}
    print(
        json.dumps(
            {
                "input": {
                    "path": str(args.csv_path),
                    "rows": n,
                    "sha256": digest,
                    "first_timestamp": stamps[0],
                    "last_timestamp": stamps[-1],
                    "backward_timestamp_anomalies": anomalies,
                    "timestamp_policy": "preserve source order; no timezone conversion because broker clock/DST convention is unverified",
                },
                "parameters": {
                    "atr_period": args.atr_period,
                    "horizon_bars": args.horizon,
                    "upper_atr": args.upper_atr,
                    "lower_atr": args.lower_atr,
                    "lookback": args.lookback,
                    "efficiency_threshold": args.efficiency_threshold,
                    "min_move_bps": args.min_move_bps,
                    "parameters_fixed_no_validation_or_holdout_tuning": True,
                },
                "split_policy": "chronological 70/15/15; events whose label window crosses a split boundary are purged; no CPCV or separate post-test embargo because later samples are not reused for training",
                "label_counts": label_counts,
                "prediction_counts": prediction_counts,
                "folds": folds,
                "limitations": [
                    "offline diagnostic only; classifier output is not a probability",
                    "no costs, slippage, confidence intervals, Brier score, LogLoss, or IC",
                    "Triple Barrier labels are target definitions, not predictors; interpret results only against a predeclared horizon and barrier specification",
                    "not evidence of profitability",
                ],
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
