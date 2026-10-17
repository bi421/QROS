"""Pre-registered kinetic + ATR triple-barrier regime diagnostic.

Reports conditional outcome frequencies only; no profitability or calibrated
probability claim. Thresholds are fixed CLI defaults and must not be tuned on 2025.
"""

from __future__ import annotations
import argparse
import hashlib
import json
from collections import deque
from datetime import datetime
from pathlib import Path
from scripts.audit_candle_velocity_m15_h1 import parse_m15
from researchos.orchestration.candle_kinetic_engine import CandleKineticEngine
from researchos.orchestration.binomial_edge import binomial_edge_test
from researchos.orchestration.kinetic_regime_filter import classify_session, volatility_gate
from researchos.orchestration.triple_barrier import triple_barrier_label


def wilder_atr(rows, period):
    tr = []
    out = [None] * len(rows)
    for i, (_, o, h, lo, c) in enumerate(rows):
        prev = rows[i - 1][4] if i else None
        tr.append(h - lo if prev is None else max(h - lo, abs(h - prev), abs(lo - prev)))
        if i == period - 1:
            out[i] = sum(tr[:period]) / period
        elif i >= period:
            out[i] = ((period - 1) * out[i - 1] + tr[i]) / period
    return tr, out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--m15", default=r"C:\Users\User\Documents\XAUUSDM15.csv")
    p.add_argument("--window", type=int, default=20)
    p.add_argument("--z-threshold", type=float, default=2.0)
    p.add_argument("--atr-period", type=int, default=14)
    p.add_argument("--upper-atr", type=float, default=1.0)
    p.add_argument("--lower-atr", type=float, default=1.0)
    p.add_argument("--vertical-barrier", type=int, default=10)
    p.add_argument("--volatility-percentile", type=float, default=0.60)
    p.add_argument("--min-vol-history", type=int, default=50)
    p.add_argument("--holdout-start", default="2025-01-01")
    p.add_argument("--holdout-end", default="2026-01-01")
    p.add_argument("--output", default="artifacts/candle_kinetic_triple_barrier_regime_audit.json")
    a = p.parse_args()
    if a.window < 2 or a.z_threshold <= 0 or a.atr_period < 2 or a.vertical_barrier < 1:
        p.error("window >= 2, z-threshold > 0, ATR period >= 2 and vertical barrier >= 1 required")
    source = Path(a.m15)
    rows = parse_m15(source)
    n = len(rows)
    tr, atr = wilder_atr(rows, a.atr_period)
    opens = [r[1] for r in rows]
    highs = [r[2] for r in rows]
    lows = [r[3] for r in rows]
    closes = [r[4] for r in rows]
    engine = CandleKineticEngine(window=a.window, z_threshold=a.z_threshold)
    prior_atrs = deque(maxlen=max(a.min_vol_history, 1000))
    hold_start = datetime.strptime(a.holdout_start, "%Y-%m-%d")
    hold_end = datetime.strptime(a.holdout_end, "%Y-%m-%d")
    groups = {}
    total = {
        "bars": 0,
        "impulses": 0,
        "directional_impulses": 0,
        "high_volatility_impulses": 0,
        "session_and_vol_filtered": 0,
        "unavailable_labels": 0,
        "ambiguous_labels": 0,
    }
    for i, (ts, o, h, lo, c) in enumerate(rows):
        f = engine.update(o, h, lo, c, interval_seconds=900.0)
        split = (
            "HOLDOUT_2025"
            if hold_start <= ts < hold_end
            else ("PRE_HOLDOUT" if ts < hold_start else "AFTER_HOLDOUT")
        )
        if datetime(2021, 1, 1) <= ts < hold_end:
            total["bars"] += 1
            if f.get("impulse"):
                total["impulses"] += 1
            if f.get("impulse") and f.get("direction") in (-1, 1):
                gate = volatility_gate(
                    list(prior_atrs),
                    float(atr[i] or 0.0),
                    min_history=a.min_vol_history,
                    percentile_floor=a.volatility_percentile,
                )
                session = classify_session(ts)
                total["directional_impulses"] += 1
                if gate["eligible"]:
                    total["high_volatility_impulses"] += 1
                if gate["eligible"] and session in ("LONDON", "NEW_YORK_OVERLAP"):
                    total["session_and_vol_filtered"] += 1
                label = triple_barrier_label(
                    opens,
                    highs,
                    lows,
                    closes,
                    atr,
                    i,
                    upper_atr=a.upper_atr,
                    lower_atr=a.lower_atr,
                    vertical_barrier=a.vertical_barrier,
                )
                if label["label"] == "UNAVAILABLE":
                    total["unavailable_labels"] += 1
                if label["label"] == "AMBIGUOUS":
                    total["ambiguous_labels"] += 1
                if split in ("PRE_HOLDOUT", "HOLDOUT_2025") and label["label"] != "UNAVAILABLE":
                    # Avoid labels crossing the fixed split boundary.
                    end_index = label["end_index"]
                    if (
                        split == "PRE_HOLDOUT"
                        and end_index is not None
                        and rows[end_index][0] >= hold_start
                    ):
                        if atr[i] is not None:
                            prior_atrs.append(atr[i])
                            continue
                    key = f"{split}|ALL_IMPULSES"
                    bucket = groups.setdefault(
                        key,
                        {
                            "events": 0,
                            "UP_FIRST": 0,
                            "DOWN_FIRST": 0,
                            "TIMEOUT": 0,
                            "AMBIGUOUS": 0,
                            "aligned_barrier": 0,
                            "adverse_barrier": 0,
                            "session_high_vol_events": 0,
                        },
                    )
                    bucket["events"] += 1
                    bucket[label["label"]] += 1
                    aligned = (label["label"] == "UP_FIRST" and f["direction"] == 1) or (
                        label["label"] == "DOWN_FIRST" and f["direction"] == -1
                    )
                    # Conservative ambiguity policy: a same-bar double touch is
                    # counted as an adverse outcome for every directional signal.
                    adverse = label["label"] == "AMBIGUOUS" or (
                        (label["label"] == "DOWN_FIRST" and f["direction"] == 1)
                        or (label["label"] == "UP_FIRST" and f["direction"] == -1)
                    )
                    bucket["aligned_barrier"] += int(aligned)
                    bucket["adverse_barrier"] += int(adverse)
                    if gate["eligible"] and session in ("LONDON", "NEW_YORK_OVERLAP"):
                        key2 = f"{split}|HIGH_VOL_LONDON_NY"
                        b = groups.setdefault(
                            key2,
                            {
                                "events": 0,
                                "UP_FIRST": 0,
                                "DOWN_FIRST": 0,
                                "TIMEOUT": 0,
                                "AMBIGUOUS": 0,
                                "aligned_barrier": 0,
                                "adverse_barrier": 0,
                                "session_high_vol_events": 0,
                            },
                        )
                        b["events"] += 1
                        b[label["label"]] += 1
                        b["session_high_vol_events"] += 1
                        b["aligned_barrier"] += int(aligned)
                        b["adverse_barrier"] += int(adverse)
        if atr[i] is not None:
            prior_atrs.append(atr[i])
    for b in groups.values():
        n_events = b["events"]
        b["aligned_barrier_rate"] = b["aligned_barrier"] / n_events if n_events else None
        b["adverse_barrier_rate"] = b["adverse_barrier"] / n_events if n_events else None
        b["timeout_rate"] = b["TIMEOUT"] / n_events if n_events else None
        hit_n = b["aligned_barrier"] + b["adverse_barrier"]
        b["directional_barrier_hits"] = hit_n
        b["aligned_rate_given_barrier_hit"] = b["aligned_barrier"] / hit_n if hit_n else None
        b["naive_exact_binomial_vs_50pct"] = (
            binomial_edge_test(
                b["aligned_barrier"], hit_n, null_probability=0.5, alternative="two-sided"
            )
            if hit_n
            else None
        )
    report = {
        "status": "COMPUTED_RESEARCH_DIAGNOSTIC_NOT_EDGE_CERTIFICATION",
        "source": {
            "path": str(source),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "rows": n,
            "first_timestamp": rows[0][0].isoformat(),
            "last_timestamp": rows[-1][0].isoformat(),
            "timestamp_timezone": "UNVERIFIED_BROKER_CLOCK; session labels are provisional",
        },
        "parameters": {
            "window": a.window,
            "z_threshold": a.z_threshold,
            "atr_period": a.atr_period,
            "upper_atr": a.upper_atr,
            "lower_atr": a.lower_atr,
            "vertical_barrier": a.vertical_barrier,
            "volatility_percentile": a.volatility_percentile,
            "min_vol_history": a.min_vol_history,
            "holdout_start": a.holdout_start,
            "holdout_end_exclusive": a.holdout_end,
            "fixed_without_holdout_tuning": True,
        },
        "counts": total,
        "conditional_outcomes": groups,
        "limitations": [
            "OHLC same-bar double touches are labeled AMBIGUOUS and conservatively counted as adverse outcomes in aligned/adverse barrier diagnostics",
            "no spread, commission, slippage, swaps, latency, or execution simulation",
            "conditional outcome frequency is not a probability forecast or net expectancy",
            "session labels are not trusted until source timezone/DST convention is verified",
            "volatility and session filters are diagnostics, not optimized selection rules",
            "2025 holdout is not used to tune parameters",
        ],
        "execution_enabled": False,
    }
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(out),
                "source": report["source"],
                "parameters": report["parameters"],
                "counts": total,
                "conditional_outcomes": groups,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
