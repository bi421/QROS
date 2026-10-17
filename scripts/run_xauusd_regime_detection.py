"""Run the XAUUSD regime detector against a local OHLC CSV and emit evidence JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from researchos.orchestration.xauusd_regime_detection import detect_market_regime


def _load_candles(path: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    raw = path.read_bytes()
    frame = pd.read_csv(path)
    normalized = {str(column).strip().lower().strip("<>"): column for column in frame.columns}
    aliases = {
        "high": ("high",),
        "low": ("low",),
        "close": ("close", "last"),
    }
    selected: dict[str, str] = {}
    for target, candidates in aliases.items():
        match = next((normalized[name] for name in candidates if name in normalized), None)
        if match is None:
            raise ValueError(f"CSV missing required column: {target}")
        selected[target] = match

    time_column = next(
        (
            normalized[name]
            for name in ("timestamp", "datetime", "date time", "time", "date")
            if name in normalized
        ),
        None,
    )
    if (
        "date" in normalized
        and "time" in normalized
        and "timestamp" not in normalized
        and "datetime" not in normalized
    ):
        timestamp_values = (
            frame[normalized["date"]].astype(str) + " " + frame[normalized["time"]].astype(str)
        )
        time_column_label = "date+time"
    elif time_column is not None:
        timestamp_values = frame[time_column]
        time_column_label = str(time_column)
    else:
        raise ValueError("CSV must include a timestamp, datetime, time, or date column")
    timestamp = pd.to_datetime(timestamp_values, errors="coerce", utc=True)
    if timestamp.isna().any():
        raise ValueError("CSV contains invalid timestamps")
    if timestamp.duplicated().any():
        raise ValueError("CSV contains duplicate timestamps")
    if not timestamp.is_monotonic_increasing:
        raise ValueError("CSV timestamps are not chronological; sort explicitly and re-run")

    candles = frame[[selected["high"], selected["low"], selected["close"]]].copy()
    candles.columns = ["high", "low", "close"]
    result_meta = {
        "input_file_name": path.name,
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "row_count": len(frame),
        "timestamp_column": time_column_label,
        "first_timestamp_utc": timestamp.iloc[0].isoformat(),
        "last_timestamp_utc": timestamp.iloc[-1].isoformat(),
        "timestamp_timezone_note": "Parsed as UTC; verify source timezone before interpreting session times.",
    }
    return candles, result_meta


def _walk_forward_transition_audit(
    labels: list[str | None], train_fraction: float = 0.7
) -> dict[str, object]:
    """Evaluate next-state probabilities using only transitions before the cutoff."""
    from math import log

    from researchos.orchestration.xauusd_regime_detection import STATES

    if not 0.5 <= train_fraction < 0.9:
        raise ValueError("train_fraction must be between 0.5 and 0.9")
    split = int(len(labels) * train_fraction)
    alpha = 1.0
    counts = {state: {next_state: alpha for next_state in STATES} for state in STATES}
    baseline = {state: alpha for state in STATES}
    for i in range(1, split):
        previous, actual = labels[i - 1], labels[i]
        if previous in STATES and actual in STATES:
            counts[previous][actual] += 1
            baseline[actual] += 1

    baseline_total = float(sum(baseline.values()))
    baseline_prob = {state: baseline[state] / baseline_total for state in STATES}
    outcomes: list[tuple[str, dict[str, float]]] = []
    for i in range(split, len(labels)):
        previous, actual = labels[i - 1], labels[i]
        if previous not in STATES or actual not in STATES:
            continue
        row = counts[previous]
        total = float(sum(row.values()))
        outcomes.append((actual, {state: row[state] / total for state in STATES}))

    if not outcomes:
        return {"status": "INSUFFICIENT_EVIDENCE", "test_transition_count": 0}

    model_loss = 0.0
    baseline_loss = 0.0
    model_brier = 0.0
    baseline_brier = 0.0
    model_correct = 0
    baseline_correct = max(STATES, key=lambda state: baseline_prob[state])
    for actual, probabilities in outcomes:
        model_loss -= log(max(probabilities[actual], 1e-15))
        baseline_loss -= log(max(baseline_prob[actual], 1e-15))
        model_brier += sum((probabilities[state] - float(state == actual)) ** 2 for state in STATES)
        baseline_brier += sum(
            (baseline_prob[state] - float(state == actual)) ** 2 for state in STATES
        )
        if max(STATES, key=lambda state: probabilities[state]) == actual:
            model_correct += 1

    n = len(outcomes)
    model_loss /= n
    baseline_loss /= n
    model_brier /= n
    baseline_brier /= n
    return {
        "status": "MEASURED_OUT_OF_SAMPLE_NOT_CALIBRATED",
        "train_fraction": train_fraction,
        "train_end_index_exclusive": split,
        "test_transition_count": n,
        "model_accuracy": model_correct / n,
        "majority_baseline_accuracy": sum(actual == baseline_correct for actual, _ in outcomes) / n,
        "model_log_loss": model_loss,
        "unconditional_baseline_log_loss": baseline_loss,
        "log_loss_skill_vs_baseline": 1.0 - model_loss / baseline_loss
        if baseline_loss > 0
        else None,
        "model_multiclass_brier": model_brier,
        "unconditional_baseline_brier": baseline_brier,
        "brier_skill_vs_baseline": 1.0 - model_brier / baseline_brier
        if baseline_brier > 0
        else None,
        "confidence_intervals": "NOT_COMPUTED",
        "interpretation_warning": "Adjacent labels use overlapping trailing windows; transition accuracy can mainly reflect label persistence, not price prediction.",
        "trading_edge_proven": False,
    }


def _forward_return_audit(
    candles: pd.DataFrame,
    labels: list[str | None],
    train_fraction: float = 0.7,
    horizons: tuple[int, ...] = (1, 5, 10),
) -> dict[str, object]:
    """Describe state-conditional forward returns in the chronological holdout."""
    if len(candles) != len(labels):
        raise ValueError("candles and labels length mismatch")
    split = int(len(labels) * train_fraction)
    close = candles["close"].to_numpy(dtype=float)
    results: dict[str, object] = {}
    for horizon in horizons:
        groups: dict[str, list[float]] = {state: [] for state in ("UP", "DOWN", "RANGE")}
        all_returns: list[float] = []
        for i in range(split, len(labels) - horizon):
            state = labels[i]
            if state not in groups:
                continue
            forward_return = float(close[i + horizon] / close[i] - 1.0)
            groups[state].append(forward_return)
            all_returns.append(forward_return)
        state_results: dict[str, object] = {}
        for state, values in groups.items():
            if not values:
                state_results[state] = {"sample_count": 0}
                continue
            mean_return = sum(values) / len(values)
            sorted_values = sorted(values)
            mid = len(sorted_values) // 2
            median_return = (
                sorted_values[mid]
                if len(sorted_values) % 2
                else (sorted_values[mid - 1] + sorted_values[mid]) / 2.0
            )
            state_results[state] = {
                "sample_count": len(values),
                "mean_forward_return": mean_return,
                "median_forward_return": median_return,
                "positive_return_rate": sum(value > 0 for value in values) / len(values),
                "directional_hit_rate": (
                    sum(value > 0 for value in values) / len(values)
                    if state == "UP"
                    else sum(value < 0 for value in values) / len(values)
                    if state == "DOWN"
                    else None
                ),
            }
        results[str(horizon)] = {
            "horizon_bars": horizon,
            "holdout_start_index": split,
            "baseline_mean_forward_return": sum(all_returns) / len(all_returns)
            if all_returns
            else None,
            "baseline_positive_return_rate": (
                sum(value > 0 for value in all_returns) / len(all_returns) if all_returns else None
            ),
            "by_state": state_results,
            "transaction_costs_included": False,
            "confidence_intervals": "NOT_COMPUTED",
        }
    return {
        "status": "DESCRIPTIVE_HOLDOUT_MEASUREMENTS_NOT_EDGE_PROOF",
        "train_fraction": train_fraction,
        "horizons": results,
        "trading_edge_proven": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lookback", type=int, default=100)
    parser.add_argument("--adx-period", type=int, default=14)
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="Evaluate transitions on the final 30%% using only earlier transition counts",
    )
    args = parser.parse_args()

    candles, metadata = _load_candles(args.csv_path)
    result = detect_market_regime(
        candles,
        lookback=args.lookback,
        adx_period=args.adx_period,
        include_history=args.walk_forward,
    )
    historical_states = result.pop("historical_states", None)
    walk_forward_audit = (
        _walk_forward_transition_audit(historical_states)
        if args.walk_forward and isinstance(historical_states, list)
        else None
    )
    forward_return_audit = (
        _forward_return_audit(candles, historical_states)
        if args.walk_forward and isinstance(historical_states, list)
        else None
    )
    report = {
        "schema_version": "1.0",
        "report_type": "xauusd_market_regime_research",
        "input": metadata,
        "result": result,
        "walk_forward_audit": walk_forward_audit,
        "forward_return_audit": forward_return_audit,
        "claims": {
            "current_state_is_heuristic": True,
            "transition_probabilities_are_calibrated_forecasts": False,
            "trading_edge_proven": False,
            "order_execution_enabled": False,
        },
    }
    output = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
        print(f"REPORT_WRITTEN={args.output}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
