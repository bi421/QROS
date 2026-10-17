"""Fixed-horizon XAUUSD impulse-strategy expectancy audit (per ounce price units).

Signals are known at M15 close i; hypothetical entry is next contiguous bar open;
exit is close at i+h. This is NOT a TP/SL strategy. Cost input is round-trip total
in XAUUSD price units per ounce (spread + entry/exit slippage + commission converted
using broker contract/lot specifications). If omitted, only gross and break-even
cost are reported; no net expectancy is claimed.
"""

from __future__ import annotations
import argparse
import json
import math
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from researchos.orchestration.candle_velocity import CandleVelocityEngine
from researchos.orchestration.net_expectancy_gate import evaluate_net_expectancy_gate
from scripts.audit_candle_velocity_m15_h1 import parse_m15


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--m15", default=r"C:\Users\User\Documents\XAUUSDM15.csv")
    p.add_argument("--window", type=int, default=20)
    p.add_argument("--z-threshold", type=float, default=2.0)
    p.add_argument("--start", default="2021-01-01")
    p.add_argument("--end", default="2025-12-31")
    p.add_argument("--holdout-start", default="2025-01-01")
    p.add_argument(
        "--roundtrip-cost-price",
        type=float,
        default=None,
        help="All-in round-trip cost in XAUUSD price units per ounce; convert spread, both-side slippage and commission using broker specifications",
    )
    p.add_argument(
        "--cost-audit-verified",
        action="store_true",
        help="Explicitly attest that the supplied all-in cost was verified against the target broker/account",
    )
    a = p.parse_args()
    if a.window < 2 or a.z_threshold <= 0:
        p.error("window >= 2 and z-threshold > 0 required")
    if a.roundtrip_cost_price is not None and (
        not math.isfinite(a.roundtrip_cost_price) or a.roundtrip_cost_price < 0
    ):
        p.error("cost must be finite and >= 0")
    if a.cost_audit_verified and a.roundtrip_cost_price is None:
        p.error("--cost-audit-verified requires --roundtrip-cost-price")
    rows = parse_m15(a.m15)
    start = datetime.strptime(a.start, "%Y-%m-%d")
    end = datetime.strptime(a.end, "%Y-%m-%d") + timedelta(days=1)
    hold = datetime.strptime(a.holdout_start, "%Y-%m-%d")
    engine = CandleVelocityEngine(window=a.window, z_threshold=a.z_threshold)
    prior = deque(maxlen=a.window)
    prev_close = prev_ts = None
    trades = {h: {"TRAIN": [], "HOLDOUT": []} for h in (3, 5)}
    gaps = 0
    signals = 0
    for i, (ts, o, hi, lo, cl) in enumerate(rows):
        contiguous = prev_ts is None or ts - prev_ts == timedelta(minutes=15)
        if not contiguous:
            gaps += 1
            engine = CandleVelocityEngine(window=a.window, z_threshold=a.z_threshold)
            prior.clear()
            prev_close = None
        feat = engine.update(o, hi, lo, cl, interval_seconds=900.0)
        tr = (
            max(hi - lo, abs(hi - prev_close), abs(lo - prev_close))
            if prev_close is not None
            else hi - lo
        )
        if (
            start <= ts < end
            and feat.get("impulse")
            and feat.get("direction") in (-1, 1)
            and len(prior) >= a.window
        ):
            d = int(feat["direction"])
            signals += 1
            split = "HOLDOUT" if ts >= hold else "TRAIN"
            for h in (3, 5):
                target = i + h
                entry_i = i + 1
                if target >= len(rows) or entry_i >= len(rows):
                    continue
                if rows[entry_i][0] - ts != timedelta(minutes=15) or rows[target][
                    0
                ] - ts != timedelta(minutes=15 * h):
                    continue
                entry = rows[entry_i][1]
                exit_price = rows[target][4]
                gross = d * (exit_price - entry)
                trades[h][split].append(
                    {"gross": gross, "win": gross > 0, "timestamp": ts.isoformat()}
                )
        prior.append(tr)
        prev_close = cl
        prev_ts = ts
    out = {
        "status": "COMPLETED_GROSS_EXPECTANCY_AUDIT",
        "source": {
            "path": a.m15,
            "rows": len(rows),
            "first_timestamp": rows[0][0].isoformat(),
            "last_timestamp": rows[-1][0].isoformat(),
            "gaps_detected": gaps,
        },
        "strategy_definition": {
            "signal": "CandleVelocityEngine impulse direction at completed M15 close",
            "entry": "next contiguous M15 bar open",
            "exit": "close at 3 or 5 M15 bars after signal",
            "position_unit": "1 troy ounce equivalent; PnL is XAUUSD price units per ounce",
            "cost_input": a.roundtrip_cost_price,
            "warning": "No TP/SL; this fixed-horizon test is not equivalent to broker account PnL. CSV contains OHLC + tick/real volume only, no spread field.",
        },
        "signals": signals,
        "horizons": {},
    }
    for h in (3, 5):
        out["horizons"][str(h)] = {}
        for split, vals in trades[h].items():
            n = len(vals)
            gross = [v["gross"] for v in vals]
            avg = sum(gross) / n if n else None
            win = sum(v["win"] for v in vals) / n if n else None
            item = {
                "n_trades": n,
                "gross_expectancy_price_per_oz": avg,
                "gross_win_rate": win,
                "gross_median_price_per_oz": sorted(gross)[n // 2] if n else None,
                "break_even_max_all_in_roundtrip_cost_price_per_oz": avg
                if avg is not None and avg > 0
                else (0.0 if avg is not None else None),
                "net_expectancy_price_per_oz": None,
                "status": "GROSS_ONLY_COSTS_NOT_PROVIDED",
            }
            if a.roundtrip_cost_price is not None and avg is not None:
                item["net_expectancy_price_per_oz"] = avg - a.roundtrip_cost_price
                item["status"] = "NET_AFTER_USER_SUPPLIED_COST_ASSUMPTION"
            out["horizons"][str(h)][split.lower()] = item
        train_gross = [v["gross"] for v in trades[h]["TRAIN"]]
        train_wins = [v for v in train_gross if v > 0]
        train_losses = [-v for v in train_gross if v < 0]
        train_outcomes = len(train_wins) + len(train_losses)
        holdout_gross = [v["gross"] for v in trades[h]["HOLDOUT"]]
        holdout_net_returns = (
            [value - a.roundtrip_cost_price for value in holdout_gross]
            if a.roundtrip_cost_price is not None
            else None
        )
        if train_outcomes and train_wins and train_losses:
            gate = evaluate_net_expectancy_gate(
                win_probability=len(train_wins) / train_outcomes,
                average_win=sum(train_wins) / len(train_wins),
                average_loss=sum(train_losses) / len(train_losses),
                roundtrip_cost=a.roundtrip_cost_price,
                costs_verified=a.cost_audit_verified,
                net_returns=holdout_net_returns,
                minimum_block_size=h,
            )
        else:
            gate = {
                "status": "NO_TRADE_INSUFFICIENT_TRAIN_PAYOFFS",
                "signal_allowed": False,
                "net_expectancy": None,
                "ci_95_percent": None,
                "reason": "training sample must contain both wins and losses",
            }
        out["horizons"][str(h)]["training_estimated_net_expectancy_gate"] = {
            **gate,
            "estimation_split": "TRAIN",
            "confidence_interval_evaluation_split": "HOLDOUT",
            "holdout_used_for_parameter_tuning": False,
            "warning": "Training estimates are frozen for this run; the chronological HOLDOUT is used only for the final net-return confidence-interval audit. Do not retune parameters after inspecting it.",
        }
    out["interpretation"] = (
        "Positive gross expectancy is not evidence of net edge until actual spread, slippage and commission are sourced from the target broker/account and applied consistently. Negative gross expectancy cannot be rescued by positive transaction costs."
    )
    target = Path("artifacts/xauusd_horizon_expectancy_audit.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": out["status"],
                "signals": signals,
                "gaps": gaps,
                "output": str(target),
                "horizons": out["horizons"],
                "cost_input": a.roundtrip_cost_price,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
