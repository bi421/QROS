"""Quantify gross-return selection bias from trades excluded for incomplete M1 exit-spread buckets."""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
engine = importlib.import_module("scripts.reassess_follow_pairs_with_trade_costs")
SOURCE_M15 = engine.SOURCE_M15
SOURCE_M1 = engine.SOURCE_M1
ORIGINAL_RERUN = engine.ORIGINAL_RERUN
COST_REPORT = ROOT / "artifacts/qros_follow_19_cost_reassessment_20261017.json"
OUTPUT = ROOT / "artifacts/qros_follow_missing_data_bias_20261017.json"
PAIR_KEYS = ("lookback", "z", "tp_atr", "sl_atr", "horizon")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe(values: np.ndarray) -> dict:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if not len(values):
        return {"n": 0, "mean": None, "median": None, "std": None, "win_rate": None, "q05": None, "q95": None}
    return {
        "n": int(len(values)),
        "mean": float(values.mean()),
        "median": float(np.median(values)),
        "std": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
        "win_rate": float(np.mean(values > 0)),
        "q05": float(np.quantile(values, 0.05)),
        "q95": float(np.quantile(values, 0.95)),
    }


def compare(values: np.ndarray, exact: np.ndarray) -> dict:
    retained = describe(values[exact])
    excluded = describe(values[~exact])
    all_stats = describe(values)
    return {
        "retained_exact_exit_spread": retained,
        "excluded_incomplete_exit_spread": excluded,
        "all_trades": all_stats,
        "excluded_minus_retained_mean_gross_return": (
            excluded["mean"] - retained["mean"]
            if excluded["mean"] is not None and retained["mean"] is not None else None
        ),
        "all_minus_retained_mean_gross_return": (
            all_stats["mean"] - retained["mean"]
            if all_stats["mean"] is not None and retained["mean"] is not None else None
        ),
        "interpretation": "Descriptive selection-bias estimate; not a causal effect or independent-trade confidence interval.",
    }


def run() -> dict:
    if not SOURCE_M15.is_file() or not SOURCE_M1.is_file():
        raise FileNotFoundError("Required frozen M15/M1 sources unavailable")
    cost_report = json.loads(COST_REPORT.read_text(encoding="utf-8-sig"))
    params_list = [item["params"] for item in cost_report["historical_19"]]
    bars, m1_sha, m1 = engine.load_spread_bars()
    original = engine.load_ohlcv_csv(SOURCE_M15)
    original_close = np.asarray(original["close"], dtype=np.float64)
    n_original = len(original_close)
    original_frame = pl.DataFrame({
        "timestamp": np.asarray(original["timestamp"]).astype("datetime64[us]"),
        "src_open": original["open"], "src_high": original["high"],
        "src_low": original["low"], "src_close": original["close"],
    })
    aligned = original_frame.join(
        bars.select("timestamp", "open", "high", "low", "close"),
        on="timestamp", how="inner",
    )
    if aligned.height != bars.height:
        raise ValueError(f"M15_ALIGNMENT_ROW_MISMATCH:{aligned.height}!={bars.height}")
    mismatch = aligned.filter(
        ((pl.col("src_open") - pl.col("open")).abs() >= 0.011)
        | ((pl.col("src_high") - pl.col("high")).abs() >= 0.011)
        | ((pl.col("src_low") - pl.col("low")).abs() >= 0.011)
        | ((pl.col("src_close") - pl.col("close")).abs() >= 0.011)
    )
    if mismatch.height:
        raise ValueError(f"M15_ALIGNMENT_OHLC_MISMATCH:{mismatch.height}")
    if len(params_list) != 19:
        raise ValueError(f"EXPECTED_19_PAIRS_GOT_{len(params_list)}")

    bars_ts = bars["timestamp"].to_numpy().astype("datetime64[ns]")
    o, h, low, close = (
        bars[k].to_numpy().astype(np.float64) for k in ("open", "high", "low", "close")
    )
    ts = bars_ts
    n = len(close)
    atr = engine._atr(h, low, close)
    score_cache = {
        lb: engine._causal_signal_score(close, atr, ts, lb)
        for lb in sorted({int(p["lookback"]) for p in params_list})
    }
    hold_start = int(n * 0.8)
    series: dict[str, dict[str, list[float]]] = {
        mode: {"retained": [], "excluded": [], "all": [], "holdout_retained": [], "holdout_excluded": []}
        for mode in ("FOLLOW_SIGNAL", "REVERSE_SIGNAL")
    }
    pair_results = []
    excluded_rows = 0
    total_trade_rows = 0
    for p in params_list:
        lb, z, tp, sl, hz = int(p["lookback"]), float(p["z"]), float(p["tp_atr"]), float(p["sl_atr"]), int(p["horizon"])
        score = score_cache[lb]
        idx = np.arange(n)
        gap = np.r_[False, np.diff(ts) != np.timedelta64(15, "m")]
        gap_prefix = np.cumsum(gap)
        contiguous = (idx + hz < n) & ((gap_prefix[np.minimum(idx + hz, n - 1)] - gap_prefix) == 0)
        sig = np.flatnonzero(np.isfinite(score) & (np.abs(score) >= z) & np.isfinite(atr) & contiguous)
        if not len(sig):
            raise ValueError(f"NO_TRADES_FOR_PARAMS:{p}")
        pair_result = {"params": p, "directions": {}}
        for mode, sign in (("FOLLOW_SIGNAL", 1.0), ("REVERSE_SIGNAL", -1.0)):
            direction = np.sign(score[sig]) * sign
            tr = engine.build_trade_arrays(bars, sig, direction, tp, sl, hz, atr, o, h, low, close, ts)
            _, _, exact = engine.resolve_exit_m1_quotes(tr, m1, ts)
            gross = tr["gross_return"].astype(np.float64)
            if len(gross) != len(exact):
                raise ValueError("GROSS_EXIT_SPREAD_MASK_LENGTH_MISMATCH")
            total_trade_rows += len(gross)
            excluded_rows += int((~exact).sum())
            mode_series = series[mode]
            mode_series["retained"].extend(gross[exact].tolist())
            mode_series["excluded"].extend(gross[~exact].tolist())
            mode_series["all"].extend(gross.tolist())
            holdout = tr["signal_ix"] >= hold_start
            mode_series["holdout_retained"].extend(gross[holdout & exact].tolist())
            mode_series["holdout_excluded"].extend(gross[holdout & ~exact].tolist())
            pair_result["directions"][mode] = {
                "trade_count": int(len(gross)),
                "excluded_count": int((~exact).sum()),
                "retained_gross": describe(gross[exact]),
                "excluded_gross": describe(gross[~exact]),
                "excluded_minus_retained_mean": (
                    float(gross[~exact].mean() - gross[exact].mean())
                    if (~exact).any() and exact.any() else None
                ),
            }
        pair_results.append(pair_result)

    by_direction = {}
    for mode, groups in series.items():
        retained = np.asarray(groups["retained"], dtype=np.float64)
        excluded = np.asarray(groups["excluded"], dtype=np.float64)
        all_values = np.asarray(groups["all"], dtype=np.float64)
        by_direction[mode] = {
            "retained_gross": describe(retained),
            "excluded_gross": describe(excluded),
            "all_gross": describe(all_values),
            "excluded_minus_retained_mean_gross_return": (
                float(excluded.mean() - retained.mean()) if len(excluded) and len(retained) else None
            ),
            "holdout_retained_gross": describe(np.asarray(groups["holdout_retained"], dtype=np.float64)),
            "holdout_excluded_gross": describe(np.asarray(groups["holdout_excluded"], dtype=np.float64)),
        }
    report = {
        "schema_version": "qros-follow-missingness-bias.v1",
        "created_utc": "2026-10-17",
        "source_m15": str(SOURCE_M15),
        "source_m15_sha256": sha256(SOURCE_M15),
        "source_m1": str(SOURCE_M1.relative_to(ROOT)),
        "source_m1_sha256": m1_sha,
        "original_m15_rows": n_original,
        "m1_derived_m15_rows": bars.height,
        "m15_alignment": {"matched_rows": aligned.height, "ohlc_mismatches": mismatch.height, "tolerance_price_units": 0.011},
        "pair_count": len(params_list),
        "direction_trade_rows_recomputed": total_trade_rows,
        "excluded_trade_rows": excluded_rows,
        "retained_trade_rows": total_trade_rows - excluded_rows,
        "excluded_fraction": excluded_rows / total_trade_rows if total_trade_rows else None,
        "by_direction": by_direction,
        "per_pair": pair_results,
        "selection_definition": "Excluded when the M15 TP/SL barrier was reached but the corresponding M1 exit bucket did not contain all 15 minutes; gross return remains observable from the original M15 engine.",
        "limitations": [
            "This is descriptive missing-data bias, not proof that missingness is random or non-random.",
            "Trade rows overlap in time; no independent-trade p-value or confidence interval is reported.",
            "The source period overlaps selection and is not an untouched holdout.",
        ],
        "execution_authorized": False,
    }
    OUTPUT.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT.relative_to(ROOT)),
        "excluded_trade_rows": excluded_rows,
        "retained_trade_rows": total_trade_rows - excluded_rows,
        "excluded_fraction": report["excluded_fraction"],
        "by_direction": {
            mode: {
                "retained": by_direction[mode]["retained_gross"],
                "excluded": by_direction[mode]["excluded_gross"],
                "mean_bias": by_direction[mode]["excluded_minus_retained_mean_gross_return"],
            } for mode in by_direction
        },
    }, indent=2))
    return report


if __name__ == "__main__":
    run()
