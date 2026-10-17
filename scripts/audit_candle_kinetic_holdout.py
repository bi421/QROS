"""2025 holdout audit for Candle Momentum & Kinetic Energy Framework.

Uses the existing XAUUSD M15 CSV and the prior audit's continuation/reversal/sideways
label definition. Impulse selection is Z-speed >= threshold. Train period ends before
2025; 2025 is not used for fitting or threshold selection. Outputs diagnostics only.
"""

from __future__ import annotations
import argparse
import json
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from researchos.orchestration.candle_kinetic_engine import CandleKineticEngine
from researchos.orchestration.logistic_probability import fit_evaluate_logistic
from scripts.audit_candle_velocity_m15_h1 import parse_m15, aggregate_h1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--m15", default=r"C:\Users\User\Documents\XAUUSDM15.csv")
    p.add_argument("--window", type=int, default=20)
    p.add_argument("--z-threshold", type=float, default=2.0)
    p.add_argument("--sideways-range-fraction", type=float, default=0.25)
    p.add_argument("--analysis-start", default="2021-01-01")
    p.add_argument("--analysis-end", default="2025-12-31")
    p.add_argument("--holdout-start", default="2025-01-01")
    p.add_argument("--output", default="artifacts/candle_kinetic_2025_holdout.json")
    a = p.parse_args()
    if a.window < 2 or a.z_threshold <= 0 or a.sideways_range_fraction < 0:
        p.error("window >= 2, z-threshold > 0 and sideways-range-fraction >= 0 required")
    rows = parse_m15(a.m15)
    h1 = aggregate_h1(rows)
    h1_closes = [(x[0] + timedelta(hours=1), x) for x in h1]
    h1_cursor = -1
    engine = CandleKineticEngine(window=a.window, z_threshold=a.z_threshold)
    prior_ranges = deque(maxlen=a.window)
    previous_close = previous_ts = None
    pending = {3: deque(), 5: deque()}
    samples = {3: {"TRAIN": [], "HOLDOUT": []}, 5: {"TRAIN": [], "HOLDOUT": []}}
    impulse_count = {"TRAIN": 0, "HOLDOUT": 0}
    eligible_count = {"TRAIN": 0, "HOLDOUT": 0}
    gaps = 0
    analysis_start = datetime.strptime(a.analysis_start, "%Y-%m-%d")
    analysis_end = datetime.strptime(a.analysis_end, "%Y-%m-%d") + timedelta(days=1)
    hold = datetime.strptime(a.holdout_start, "%Y-%m-%d")
    for i, (ts, o, high, low, close) in enumerate(rows):
        contiguous = previous_ts is None or ts - previous_ts == timedelta(minutes=15)
        if not contiguous:
            gaps += 1
            for h in (3, 5):
                pending[h].clear()
            engine.reset()
            prior_ranges.clear()
            previous_close = None
        event_close = ts + timedelta(minutes=15)
        while h1_cursor + 1 < len(h1_closes) and h1_closes[h1_cursor + 1][0] <= event_close:
            h1_cursor += 1
        h1_dir = None
        if h1_cursor >= 0:
            bar = h1_closes[h1_cursor][1]
            h1_dir = 1 if bar[4] > bar[1] else -1 if bar[4] < bar[1] else 0
        # Resolve labels before registering the current event.
        for horizon in (3, 5):
            while pending[horizon] and pending[horizon][0]["target_index"] <= i:
                event = pending[horizon].popleft()
                if event["target_index"] != i:
                    continue
                directional_move = event["direction"] * (close - event["close"])
                outcome = (
                    "CONTINUATION"
                    if directional_move > event["sideways_threshold"]
                    else "REVERSAL"
                    if directional_move < -event["sideways_threshold"]
                    else "SIDEWAYS"
                )
                if outcome not in ("CONTINUATION", "REVERSAL"):
                    continue
                split = "HOLDOUT" if event["timestamp"] >= hold else "TRAIN"
                samples[horizon][split].append(
                    {**event["features"], "label": 1 if outcome == "CONTINUATION" else 0}
                )
        feat = engine.update(o, high, low, close, interval_seconds=900.0)
        true_range = (
            max(high - low, abs(high - previous_close), abs(low - previous_close))
            if previous_close is not None
            else high - low
        )
        in_analysis = analysis_start <= ts < analysis_end
        split = "HOLDOUT" if ts >= hold else "TRAIN"
        if in_analysis:
            eligible_count[split] += 1
            if feat.get("impulse"):
                impulse_count[split] += 1
        if (
            in_analysis
            and feat.get("impulse")
            and feat.get("direction") in (-1, 1)
            and prior_ranges
            and h1_dir in (-1, 0, 1)
        ):
            direction = int(feat["direction"])
            align = 1.0 if h1_dir == direction else 0.0
            features = {
                "z_speed": float(feat["z_speed"]),
                "body_ratio": float(feat["body_ratio"]),
                "upper_wick_ratio": float(feat["upper_ratio"]),
                "lower_wick_ratio": float(feat["lower_ratio"]),
                "h1_aligned": align,
            }
            threshold = a.sideways_range_fraction * (sum(prior_ranges) / len(prior_ranges))
            for horizon in (3, 5):
                target = i + horizon
                if target < len(rows) and rows[target][0] - ts == timedelta(minutes=15 * horizon):
                    pending[horizon].append(
                        {
                            "target_index": target,
                            "timestamp": ts,
                            "direction": direction,
                            "close": close,
                            "sideways_threshold": threshold,
                            "features": features,
                        }
                    )
        prior_ranges.append(true_range)
        previous_close, previous_ts = close, ts
    report = {
        "status": "COMPLETED_EMPIRICAL_HOLDOUT_AUDIT",
        "source": {
            "path": a.m15,
            "rows": len(rows),
            "first_timestamp": rows[0][0].isoformat(),
            "last_timestamp": rows[-1][0].isoformat(),
            "gaps_detected": gaps,
        },
        "framework": "Candle Momentum & Kinetic Energy Framework",
        "parameters": {
            "window": a.window,
            "z_threshold": a.z_threshold,
            "sideways_range_fraction": a.sideways_range_fraction,
            "analysis_start": a.analysis_start,
            "analysis_end": a.analysis_end,
            "holdout_start": a.holdout_start,
        },
        "definitions": {
            "range_velocity": "(high-low)/900 seconds",
            "z_speed": "(current range velocity - prior rolling mean)/prior rolling population standard deviation; current bar excluded",
            "range_acceleration_proxy": "difference in range velocity divided by 900 seconds",
            "range_energy_proxy": "0.5 * range_velocity^2; analogy/proxy only, not physical energy",
            "label": "directional move from signal close to close h bars later; continuation/reversal require move beyond +/- 0.25 * prior rolling mean true range; sideways labels excluded from logistic metrics",
            "warning": "Only completed candles; features do not directly observe order flow or liquidity. Impulse prevalence is a sample statistic, not a noise-removal guarantee.",
        },
        "splits": {},
        "horizons": {},
    }
    for split in ("TRAIN", "HOLDOUT"):
        n = eligible_count[split]
        k = impulse_count[split]
        report["splits"][split.lower()] = {
            "bars": n,
            "impulse_bars": k,
            "impulse_fraction": k / n if n else None,
            "threshold": "z_speed >= configured threshold",
        }
    for h in (3, 5):
        train = samples[h]["TRAIN"]
        test = samples[h]["HOLDOUT"]
        model = fit_evaluate_logistic(train, test, l2=1.0)
        report["horizons"][str(h)] = {
            "bars": h,
            "train_directional_events": len(train),
            "holdout_2025_directional_events": len(test),
            "model": model,
            "economic_expectancy": "NOT_TESTED_BY_THIS_SCRIPT; use broker-verified round-trip cost and execution-aligned entry/exit simulation",
        }
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(out),
                "source": report["source"],
                "splits": report["splits"],
                "horizons": {
                    h: {
                        "train_n": v["train_directional_events"],
                        "holdout_n": v["holdout_2025_directional_events"],
                        "model_status": v["model"]["status"],
                        "holdout_metrics": v["model"].get("holdout_metrics"),
                        "baseline_metrics": v["model"].get(
                            "holdout_train_prevalence_baseline_metrics"
                        ),
                    }
                    for h, v in report["horizons"].items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
