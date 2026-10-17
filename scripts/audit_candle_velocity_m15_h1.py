"""Empirical M15 candle-velocity audit with H1 context aggregated from same M15 source.

This is a research-frequency audit, not a calibrated forecast or PnL test.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

from researchos.orchestration.candle_velocity import CandleVelocityEngine
from researchos.orchestration.binomial_edge import binomial_edge_test
from researchos.orchestration.logistic_probability import fit_evaluate_logistic
from researchos.orchestration.purged_walk_forward import purged_walk_forward_evaluate
from researchos.orchestration.statistical_validation import (
    benjamini_hochberg,
    effective_sample_size,
    lag_autocorrelation,
)

OUTCOMES = ("CONTINUATION", "REVERSAL", "SIDEWAYS")


def validate_ohlc(line_no, o, high, low, close):
    vals = (o, high, low, close)
    if not all(math.isfinite(x) and x > 0 for x in vals):
        raise ValueError(f"row {line_no}: OHLC must be finite and positive")
    if high < max(o, close, low) or low > min(o, close, high):
        raise ValueError(f"row {line_no}: invalid OHLC ordering")


def parse_m15(path):
    rows = []
    with Path(path).open("r", newline="", encoding="utf-16") as f:
        for line_no, row in enumerate(csv.reader(f), 1):
            if not row:
                continue
            if len(row) < 5:
                raise ValueError(f"M15 row {line_no}: expected timestamp, open, high, low, close")
            ts = datetime.strptime(row[0].strip(), "%Y.%m.%d %H:%M")
            o, high, low, close = map(float, row[1:5])
            validate_ohlc(line_no, o, high, low, close)
            rows.append((ts, o, high, low, close))
    if not rows:
        raise ValueError("M15 CSV contains no rows")
    if any(rows[i][0] >= rows[i + 1][0] for i in range(len(rows) - 1)):
        raise ValueError("M15 timestamps must be strictly increasing")
    return rows


def aggregate_h1(m15):
    """Aggregate only complete, contiguous four-candle H1 bars from M15."""
    buckets = {}
    for bar in m15:
        ts = bar[0]
        hour = ts.replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(hour, []).append(bar)
    h1 = []
    for hour, bars in sorted(buckets.items()):
        expected = [hour + timedelta(minutes=15 * n) for n in range(4)]
        if [bar[0] for bar in bars] != expected:
            continue
        h1.append((hour, bars[0][1], max(x[2] for x in bars), min(x[3] for x in bars), bars[-1][4]))
    if not h1:
        raise ValueError("No complete H1 bars can be aggregated from M15 source")
    return h1


def empty_counts():
    return {k: 0 for k in OUTCOMES}


def daily_cluster_bootstrap(daily_counts, split, iterations=2000, seed=20261016):
    """Percentile CI by resampling whole event-days, preserving within-day dependence."""
    days = [v for (day_split, _), v in sorted(daily_counts.items()) if day_split == split]
    total = {k: sum(day[k] for day in days) for k in OUTCOMES}
    n = sum(total.values())
    if not days or n == 0:
        return {"n_days": len(days), "n_events": n, "intervals_95pct": {}}
    rng = random.Random(seed)
    samples = {k: [] for k in OUTCOMES}
    for _ in range(iterations):
        selected = [days[rng.randrange(len(days))] for _ in range(len(days))]
        denom = sum(sum(day.values()) for day in selected)
        if not denom:
            continue
        for outcome in OUTCOMES:
            samples[outcome].append(sum(day[outcome] for day in selected) / denom)
    intervals = {}
    for outcome in OUTCOMES:
        values = sorted(samples[outcome])
        lo = values[int(0.025 * (len(values) - 1))]
        hi = values[int(0.975 * (len(values) - 1))]
        intervals[outcome] = {"estimate": total[outcome] / n, "lower_95pct": lo, "upper_95pct": hi}
    return {
        "n_days": len(days),
        "n_events": n,
        "bootstrap_iterations": iterations,
        "method": "percentile bootstrap resampling event-days within split",
        "intervals_95pct": intervals,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--m15", default=r"C:\Users\User\Documents\XAUUSDM15.csv")
    p.add_argument("--window", type=int, default=20)
    p.add_argument("--z-threshold", type=float, default=2.0)
    p.add_argument("--sideways-range-fraction", type=float, default=0.25)
    p.add_argument("--analysis-start", default="2021-01-01")
    p.add_argument("--analysis-end", default="2025-12-31")
    p.add_argument("--holdout-start", default="2025-01-01")
    p.add_argument("--output", default="artifacts/candle_velocity_m15_h1_audit.json")
    a = p.parse_args()
    if a.window < 2 or a.z_threshold <= 0 or a.sideways_range_fraction < 0:
        p.error("window >= 2, z-threshold > 0, sideways-range-fraction >= 0 required")

    m15 = parse_m15(a.m15)
    h1 = aggregate_h1(m15)
    # H1 open timestamp plus one hour must be <= M15 event close time.
    h1_closes = [(row[0] + timedelta(hours=1), row) for row in h1]
    h1_cursor = -1
    engine = CandleVelocityEngine(window=a.window, z_threshold=a.z_threshold)
    prior_ranges = deque(maxlen=a.window)
    previous_close = previous_ts = None
    gaps = 0
    pending = {3: deque(), 5: deque()}
    counts = {3: {}, 5: {}}
    daily_counts = {h: {} for h in (3, 5)}
    directional_sequences = {h: {"TRAIN": [], "HOLDOUT": []} for h in (3, 5)}
    logistic_rows = {h: {"TRAIN": [], "HOLDOUT": []} for h in (3, 5)}
    resolved = {3: 0, 5: 0}
    excluded = {3: 0, 5: 0}
    start = datetime.strptime(a.analysis_start, "%Y-%m-%d")
    end = datetime.strptime(a.analysis_end, "%Y-%m-%d") + timedelta(days=1)
    holdout = datetime.strptime(a.holdout_start, "%Y-%m-%d")

    for i, (ts, o, high, low, close) in enumerate(m15):
        contiguous = previous_ts is None or ts - previous_ts == timedelta(minutes=15)
        if not contiguous:
            gaps += 1
            for horizon in (3, 5):
                excluded[horizon] += len(pending[horizon])
                pending[horizon].clear()
            engine = CandleVelocityEngine(window=a.window, z_threshold=a.z_threshold)
            prior_ranges.clear()
            previous_close = None

        event_close = ts + timedelta(minutes=15)
        while h1_cursor + 1 < len(h1_closes) and h1_closes[h1_cursor + 1][0] <= event_close:
            h1_cursor += 1
        h1_dir = None
        if h1_cursor >= 0:
            _, bar = h1_closes[h1_cursor]
            h1_dir = 1 if bar[4] > bar[1] else -1 if bar[4] < bar[1] else 0

        for horizon in (3, 5):
            while pending[horizon] and pending[horizon][0]["target_index"] <= i:
                e = pending[horizon].popleft()
                if e["target_index"] != i:
                    excluded[horizon] += 1
                    continue
                directional_move = e["direction"] * (close - e["close"])
                threshold = e["sideways_threshold"]
                outcome = (
                    "CONTINUATION"
                    if directional_move > threshold
                    else "REVERSAL"
                    if directional_move < -threshold
                    else "SIDEWAYS"
                )
                split = "HOLDOUT" if e["timestamp"] >= holdout else "TRAIN"
                key = f"{split}|{e['group']}"
                group = counts[horizon].setdefault(key, empty_counts())
                group[outcome] += 1
                day_key = (split, e["timestamp"].date().isoformat())
                day = daily_counts[horizon].setdefault(day_key, empty_counts())
                day[outcome] += 1
                if outcome in ("CONTINUATION", "REVERSAL"):
                    directional_sequences[horizon][split].append(
                        1.0 if outcome == "CONTINUATION" else 0.0
                    )
                    logistic_rows[horizon][split].append(
                        {
                            **e["model_features"],
                            "label": 1 if outcome == "CONTINUATION" else 0,
                            "timestamp": e["timestamp"].isoformat(),
                            "label_end_timestamp": e["label_end_timestamp"],
                        }
                    )
                resolved[horizon] += 1

        features = engine.update(o, high, low, close, interval_seconds=900.0)
        true_range = (
            max(high - low, abs(high - previous_close), abs(low - previous_close))
            if previous_close is not None
            else high - low
        )
        mean_range = sum(prior_ranges) / len(prior_ranges) if prior_ranges else None

        if (
            start <= ts < end
            and features.get("impulse")
            and features.get("direction") in (-1, 1)
            and mean_range is not None
            and h1_dir in (-1, 0, 1)
        ):
            d = int(features["direction"])
            align = "ALIGNED" if h1_dir == d else "OPPOSED" if h1_dir == -d else "H1_FLAT"
            group = f"M15_{'UP' if d > 0 else 'DOWN'}|{features.get('wick_pattern', 'UNKNOWN')}|H1_{align}"
            threshold = a.sideways_range_fraction * mean_range
            for horizon in (3, 5):
                target = i + horizon
                if target < len(m15) and m15[target][0] - ts == timedelta(minutes=15 * horizon):
                    pending[horizon].append(
                        {
                            "target_index": target,
                            "timestamp": ts,
                            "label_end_timestamp": (
                                m15[target][0] + timedelta(minutes=15)
                            ).isoformat(),
                            "direction": d,
                            "close": close,
                            "sideways_threshold": threshold,
                            "group": group,
                            "model_features": {
                                "z_speed": float(features["z_speed"]),
                                "body_ratio": float(features["body_ratio"]),
                                "upper_wick_ratio": float(features["upper_wick_ratio"]),
                                "lower_wick_ratio": float(features["lower_wick_ratio"]),
                                "h1_aligned": 1.0 if align == "ALIGNED" else 0.0,
                            },
                        }
                    )
                else:
                    excluded[horizon] += 1

        prior_ranges.append(true_range)
        previous_close, previous_ts = close, ts

    for horizon in (3, 5):
        excluded[horizon] += len(pending[horizon])

    horizon_report = {}
    for horizon in (3, 5):
        groups = {}
        for key, c in sorted(counts[horizon].items()):
            n = sum(c.values())
            groups[key] = {
                "n": n,
                "counts": c,
                "empirical_frequencies": {k: c[k] / n for k in OUTCOMES},
            }
        split_summary = {}
        group_test_rows = {"TRAIN": [], "HOLDOUT": []}
        for group_key, group_counts in sorted(counts[horizon].items()):
            group_split, _ = group_key.split("|", 1)
            directional_n = group_counts["CONTINUATION"] + group_counts["REVERSAL"]
            if directional_n:
                group_test_rows[group_split].append(
                    {
                        "group": group_key,
                        "test": binomial_edge_test(
                            group_counts["CONTINUATION"],
                            directional_n,
                            null_probability=0.5,
                            alternative="two-sided",
                        ),
                    }
                )
        for split in ("TRAIN", "HOLDOUT"):
            split_counts = {
                k: sum(v[k] for (s, _), v in daily_counts[horizon].items() if s == split)
                for k in OUTCOMES
            }
            n_split = sum(split_counts.values())
            directional_trials = split_counts["CONTINUATION"] + split_counts["REVERSAL"]
            # Binary comparison only among non-sideways labels; H0 is 50/50.
            # This is a diagnostic test, not evidence of profitability; event dependence remains a caveat.
            directional_test = (
                binomial_edge_test(
                    split_counts["CONTINUATION"],
                    directional_trials,
                    null_probability=0.5,
                    alternative="two-sided",
                )
                if directional_trials
                else None
            )
            directional_series = directional_sequences[horizon][split]
            rho1 = lag_autocorrelation(directional_series)
            ess = (
                effective_sample_size(len(directional_series), rho1)
                if directional_series
                else {
                    "n": 0,
                    "lag1_autocorrelation": None,
                    "n_effective_approx": None,
                    "method": "not available: no directional outcomes",
                }
            )
            split_group_tests = group_test_rows[split]
            bh_results = benjamini_hochberg(
                [row["test"]["exact_p_value"] for row in split_group_tests], q=0.05
            )
            group_tests_corrected = []
            for row, corrected in zip(split_group_tests, bh_results):
                group_tests_corrected.append(
                    {
                        "group": row["group"],
                        "raw_p_value": corrected["p_value"],
                        "bh_adjusted_p_value": corrected["p_adjusted_bh"],
                        "bh_reject_at_q_0_05": corrected["reject_at_q"],
                        "directional_n": row["test"]["trials"],
                        "continuation_rate": row["test"]["observed_rate"],
                    }
                )
            split_summary[split.lower()] = {
                "n": n_split,
                "counts": split_counts,
                "empirical_frequencies": {k: split_counts[k] / n_split for k in OUTCOMES}
                if n_split
                else {},
                "daily_cluster_bootstrap_95pct": daily_cluster_bootstrap(
                    daily_counts[horizon], split
                ),
                "continuation_vs_reversal_binomial_test": directional_test,
                "directional_outcome_dependence": {
                    "n_directional_events": len(directional_series),
                    "lag1_autocorrelation": rho1,
                    "effective_sample_size_approximation": ess,
                    "warning": "ESS is a lag-1 AR(1) diagnostic only; p-values are not mechanically adjusted by substituting ESS for N. Use block bootstrap for uncertainty under serial dependence.",
                },
                "group_binomial_tests_bh_fdr": {
                    "family_size": len(group_tests_corrected),
                    "q": 0.05,
                    "method": "Benjamini-Hochberg within this horizon and split; interpret as exploratory, especially under dependent tests",
                    "tests": group_tests_corrected,
                },
            }
        logistic_report = fit_evaluate_logistic(
            logistic_rows[horizon]["TRAIN"], logistic_rows[horizon]["HOLDOUT"]
        )
        # Keep the 2025 HOLDOUT completely outside walk-forward model development.
        walk_forward_rows = sorted(
            logistic_rows[horizon]["TRAIN"], key=lambda row: row["timestamp"]
        )
        walk_forward_report = purged_walk_forward_evaluate(
            walk_forward_rows, n_splits=4, min_train_rows=100
        )
        horizon_report[str(horizon)] = {
            "bars": horizon,
            "minutes": 15 * horizon,
            "continuation_logistic_model": logistic_report,
            "purged_walk_forward_validation": walk_forward_report,
            "resolved_events": resolved[horizon],
            "excluded_unresolved_or_gap_events": excluded[horizon],
            "split_summary": split_summary,
            "groups": groups,
        }

    result = {
        "status": "COMPLETED_EMPIRICAL_AUDIT",
        "source": {
            "m15_path": str(a.m15),
            "m15_rows": len(m15),
            "first_timestamp": str(m15[0][0]),
            "last_timestamp": str(m15[-1][0]),
            "aggregated_complete_h1_rows": len(h1),
            "h1_source": "aggregated from the same M15 file; complete contiguous four-bar hours only",
        },
        "specification": {
            "base_timeframe": "M15",
            "context_timeframe": "H1 aggregated from M15",
            "window": a.window,
            "z_threshold": a.z_threshold,
            "sideways_threshold": f"{a.sideways_range_fraction} * prior rolling mean M15 true range",
            "analysis_start": a.analysis_start,
            "analysis_end_inclusive": a.analysis_end,
            "holdout_start": a.holdout_start,
            "label": "direction-adjusted close-to-close move at horizon; continuation/reversal thresholds symmetric",
            "h1_policy": "only aggregated H1 candles closed by the M15 event candle close are used",
            "timestamp_policy": "source naive timestamps, no timezone/DST conversion; gaps reset rolling state and pending labels",
            "limitations": [
                "empirical conditional frequencies, not calibrated predictions",
                "daily-cluster bootstrap intervals are uncertainty estimates, not proof of predictive edge",
                "no spread, commission, slippage, or profitability calculation",
                "OHLC does not reveal institutional order flow",
            ],
        },
        "m15_gaps_detected": gaps,
        "horizons": horizon_report,
    }
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "m15_rows": len(m15),
                "h1_rows_aggregated": len(h1),
                "m15_gaps_detected": gaps,
                "horizons": {
                    h: {
                        "resolved": horizon_report[h]["resolved_events"],
                        "excluded": horizon_report[h]["excluded_unresolved_or_gap_events"],
                        "groups": len(horizon_report[h]["groups"]),
                    }
                    for h in horizon_report
                },
                "output": str(out),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
