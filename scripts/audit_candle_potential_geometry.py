"""Empirical first-touch barrier audit; 2025 is untouched holdout.

Reports conditional event frequencies only. It does not claim profitability or fit
barriers on holdout. Barrier width is a fixed multiple of prior rolling true range.
"""

from __future__ import annotations
import argparse
import json
import math
from collections import deque, Counter
from datetime import datetime, timedelta
from pathlib import Path
from researchos.orchestration.candle_kinetic_engine import CandleKineticEngine
from researchos.orchestration.candle_potential_geometry import (
    potential_geometry_features,
    first_touch_barrier_label,
)
from scripts.audit_candle_velocity_m15_h1 import parse_m15


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--m15", default=r"C:\Users\User\Documents\XAUUSDM15.csv")
    p.add_argument("--window", type=int, default=20)
    p.add_argument("--z-threshold", type=float, default=2.0)
    p.add_argument("--barrier-range-multiple", type=float, default=1.0)
    p.add_argument("--horizon", type=int, default=12)
    p.add_argument("--output", default="artifacts/candle_potential_geometry_2025_holdout.json")
    a = p.parse_args()
    if a.window < 2 or a.z_threshold <= 0 or a.barrier_range_multiple <= 0 or a.horizon < 1:
        p.error("window >= 2, positive z-threshold/barrier multiple, horizon >= 1 required")
    rows = parse_m15(a.m15)
    engine = CandleKineticEngine(window=a.window, z_threshold=a.z_threshold)
    ranges = deque(maxlen=a.window)
    returns = deque(maxlen=a.window)
    previous_close = None
    previous_ts = None
    ema = None
    ema_alpha = 2 / (a.window + 1)
    records = []
    gaps = 0
    future_bars = [(x[2], x[3], x[4]) for x in rows]
    for i, (ts, o, h, low, c) in enumerate(rows):
        if previous_ts is not None and ts - previous_ts != timedelta(minutes=15):
            engine.reset()
            ranges.clear()
            returns.clear()
            previous_close = None
            ema = None
            gaps += 1
        event_split = "holdout" if datetime(2025, 1, 1) <= ts < datetime(2026, 1, 1) else "train"
        if ema is None:
            ema = c
        else:
            ema = ema_alpha * c + (1 - ema_alpha) * ema
        feat = engine.update(o, h, low, c, interval_seconds=900)
        tr = (
            max(h - low, abs(h - previous_close), abs(low - previous_close))
            if previous_close is not None
            else h - low
        )
        current_return = math.log(c / previous_close) if previous_close is not None else 0.0
        scale = math.sqrt(sum(x * x for x in returns) / len(returns)) if returns else 0.0
        geo = potential_geometry_features(
            close=c,
            ema=ema,
            prior_log_returns=list(returns),
            current_log_return=current_return,
            prior_return_scale=scale,
            range_velocity=float(feat["range_velocity"]),
        )
        # Use only past range observations to set barriers; no same-bar range leakage.
        barrier_scale = (sum(ranges) / len(ranges)) if ranges else None
        label = None
        future_contiguous = i + a.horizon < len(rows) and all(
            rows[j + 1][0] - rows[j][0] == timedelta(minutes=15) for j in range(i, i + a.horizon)
        )
        if barrier_scale is not None and barrier_scale > 0 and future_contiguous:
            # Symmetric barriers around signal close; direction is evaluated separately from first-touch side.
            width = a.barrier_range_multiple * barrier_scale
            # Precomputed once above to keep this audit linear in rows times horizon.
            label = first_touch_barrier_label(future_bars, i, c + width, c - width, a.horizon)
        direction = int(feat["direction"])
        directional_label = (
            "CONTINUATION"
            if (label == "UP_FIRST" and direction == 1)
            or (label == "DOWN_FIRST" and direction == -1)
            else "REVERSAL"
            if (label == "DOWN_FIRST" and direction == 1)
            or (label == "UP_FIRST" and direction == -1)
            else label
            if label in ("AMBIGUOUS", "TIMEOUT")
            else None
        )
        records.append(
            {
                "timestamp": ts.isoformat(),
                "split": event_split,
                "impulse": bool(feat.get("impulse")),
                "direction": direction,
                "geometry": geo,
                "barrier_label": label,
                "directional_label": directional_label,
            }
        )
        ranges.append(tr)
        if previous_close is not None:
            returns.append(current_return)
        previous_close, previous_ts = c, ts
    report = {
        "status": "COMPLETED_FIRST_TOUCH_EMPIRICAL_AUDIT",
        "source": {
            "path": a.m15,
            "rows": len(rows),
            "first_timestamp": rows[0][0].isoformat(),
            "last_timestamp": rows[-1][0].isoformat(),
            "gaps_detected": gaps,
        },
        "parameters": {
            "window": a.window,
            "z_threshold": a.z_threshold,
            "barrier_range_multiple": a.barrier_range_multiple,
            "horizon_bars": a.horizon,
            "holdout": "2025-01-01 through 2025-12-31",
        },
        "caveats": [
            "Potential and kinetic values are dimensionless statistical proxies, not physical energy.",
            "Curvature is a finite-difference proxy on scaled log returns, not a proof of reversal.",
            "Barrier labels use OHLC; if both barriers touch in one candle, the event is AMBIGUOUS.",
            "No spread/commission/slippage data; no net expectancy or profitability claim.",
            "Thresholds are fixed defaults, not optimized on 2025.",
        ],
        "splits": {},
    }
    for split in ("train", "holdout"):
        subset = [
            r
            for r in records
            if r["split"] == split
            and datetime.fromisoformat(r["timestamp"]) >= datetime(2021, 1, 1)
            and datetime.fromisoformat(r["timestamp"]) < datetime(2026, 1, 1)
        ]
        for group, events in [("all", subset), ("impulse", [r for r in subset if r["impulse"]])]:
            labelled = [r for r in events if r["directional_label"] is not None]
            counts = Counter(r["directional_label"] for r in labelled)
            n = len(labelled)
            report["splits"].setdefault(split, {})[group] = {
                "bars": len(events),
                "labelled_events": n,
                "label_counts": dict(counts),
                "label_fractions": {k: v / n for k, v in counts.items()} if n else {},
            }
            valid = [r for r in events if r["geometry"]["path_curvature_proxy"] is not None]
            report["splits"][split][group]["mean_abs_curvature_proxy"] = (
                sum(abs(r["geometry"]["path_curvature_proxy"]) for r in valid) / len(valid)
                if valid
                else None
            )
            ratios = [
                r["geometry"]["kinetic_potential_ratio"]
                for r in events
                if r["geometry"]["kinetic_potential_ratio"] is not None
            ]
            report["splits"][split][group]["median_kinetic_potential_ratio"] = (
                sorted(ratios)[len(ratios) // 2] if ratios else None
            )
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(out),
                "source": report["source"],
                "parameters": report["parameters"],
                "splits": report["splits"],
                "caveats": report["caveats"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
