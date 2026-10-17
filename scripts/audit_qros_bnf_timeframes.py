"""Measure causal BNF-style diagnostics on frozen XAUUSD M1 data resampled to M15/H1/H4/D1.

Outputs gross forward-return diagnostics only. This script does not validate costs or certify an edge.
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

import polars as pl

from researchos.orchestration.qros_research_controls import apply_bnf_mean_reversion

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "mt5" / "xauusd" / "XAUUSD_M1_2021_2025_MT5.csv"
DEFAULT_OUTPUT = ROOT / "artifacts" / "qros_bnf_timeframe_diagnostics_20261017.json"
TIMEFRAMES = {"M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(ordered))
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def _load_m1(path: Path) -> tuple[pl.DataFrame, str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    frame = pl.read_csv(path, try_parse_dates=False)
    if {"time", "open", "high", "low", "close", "tick_volume"}.issubset(frame.columns):
        frame = frame.rename({"time": "timestamp", "tick_volume": "volume"})
        frame = frame.with_columns(
            pl.col("timestamp").str.to_datetime(strict=True, time_zone="UTC"),
            pl.col("open").cast(pl.Float64), pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64), pl.col("close").cast(pl.Float64),
            pl.col("volume").cast(pl.Float64),
        ).select("timestamp", "open", "high", "low", "close", "volume")
    else:
        required = {"Date", "Time", "Open", "High", "Low", "Close", "Volume"}
        if not required.issubset(frame.columns):
            raise ValueError(f"Expected MT5 columns missing: {sorted(required - set(frame.columns))}")
        frame = frame.with_columns(
            pl.concat_str([pl.col("Date"), pl.lit(" "), pl.col("Time")])
            .str.to_datetime(format="%Y.%m.%d %H:%M:%S", strict=True)
            .alias("timestamp"),
            pl.col("Open").cast(pl.Float64).alias("open"),
            pl.col("High").cast(pl.Float64).alias("high"),
            pl.col("Low").cast(pl.Float64).alias("low"),
            pl.col("Close").cast(pl.Float64).alias("close"),
            pl.col("Volume").cast(pl.Float64).alias("volume"),
        ).select("timestamp", "open", "high", "low", "close", "volume")
    frame = frame.sort("timestamp")
    if frame["timestamp"].n_unique() != frame.height:
        raise ValueError("Duplicate M1 timestamps found")
    return frame, digest


def _timeframe_report(frame: pl.DataFrame, timeframe: str, every: str) -> dict[str, Any]:
    bars = (
        frame.group_by_dynamic("timestamp", every=every, closed="left", label="left")
        .agg([
            pl.col("open").first(), pl.col("high").max(), pl.col("low").min(),
            pl.col("close").last(), pl.col("volume").sum(),
        ])
        .drop_nulls("close")
        .sort("timestamp")
    )
    # A fixed 500-bar historical quantile window; thresholds are shifted one bar,
    # so a signal cannot use its own z-score to set its threshold.
    signals = apply_bnf_mean_reversion(
        bars.select("timestamp", "close", "volume"),
        window_size=25, quantile_window=500, quantile_min_samples=100,
        strong_quantile=0.01, candidate_quantile=0.05,
    )
    labels = signals["bnf_signal"].to_list()
    close = signals["close"].to_list()
    count = len(labels)
    strong_signal_indices = [i for i, value in enumerate(labels) if value == "BUY_STRONG"]
    strong_indices = [i for i in strong_signal_indices if i < max(0, count - 5)]
    candidate_indices = [i for i, value in enumerate(labels) if value == "CANDIDATE"]
    no_trade_count = sum(value == "NO_TRADE" for value in labels)

    z_values_all = signals["zscore"].to_list()
    strong_thresholds = signals["strong_threshold"].to_list()
    candidate_thresholds = signals["candidate_threshold"].to_list()
    eligible_indices = [
        i for i in range(max(0, count - 5))
        if z_values_all[i] is not None and strong_thresholds[i] is not None
        and candidate_thresholds[i] is not None and close[i] > 0
    ]
    control_count = min(len(strong_indices), len(eligible_indices))
    seed = 20261017 + {"M15": 15, "H1": 60, "H4": 240, "D1": 1440}[timeframe]
    rng = random.Random(seed)
    random_entry_indices = rng.sample(eligible_indices, control_count) if control_count else []
    shuffled_labels = [labels[i] for i in eligible_indices]
    rng.shuffle(shuffled_labels)
    shuffled_signal_indices = [
        i for i, label in zip(eligible_indices, shuffled_labels) if label == "BUY_STRONG"
    ][:control_count]

    def return_summary(indices: list[int], horizon: int) -> dict[str, Any]:
        returns = [
            close[i + horizon] / close[i] - 1.0
            for i in indices
            if i + horizon < count and close[i] > 0 and close[i + horizon] > 0
        ]
        return {
            "horizon_bars": horizon,
            "sample_count": len(returns),
            "mean_gross_return": sum(returns) / len(returns) if returns else None,
            "median_gross_return": _quantile(returns, 0.50),
            "p10_gross_return": _quantile(returns, 0.10),
            "p90_gross_return": _quantile(returns, 0.90),
            "positive_fraction": sum(value > 0 for value in returns) / len(returns) if returns else None,
            "costs_included": False,
        }

    forward: dict[str, Any] = {}
    negative_controls: dict[str, Any] = {}
    for horizon in (1, 3, 5):
        forward[str(horizon)] = return_summary(strong_indices, horizon)
        negative_controls[str(horizon)] = {
            "random_entry_same_sample_count": return_summary(random_entry_indices, horizon),
            "shuffled_signal_same_sample_count": return_summary(shuffled_signal_indices, horizon),
            "seed": seed,
            "interpretation": "NEGATIVE_CONTROL_GROSS_DIAGNOSTIC_NOT_A_SIGNIFICANCE_TEST",
        }
    z_values = [float(value) for value in signals["zscore"].to_list() if value is not None and value == value]
    return {
        "timeframe": timeframe,
        "bars": count,
        "strong_signal_count": len(strong_signal_indices),
        "candidate_signal_count": len(candidate_indices),
        "no_trade_count": no_trade_count,
        "no_trade_fraction": no_trade_count / count if count else None,
        "strong_signal_fraction": len(strong_signal_indices) / count if count else None,
        "candidate_signal_fraction": len(candidate_indices) / count if count else None,
        "zscore_min": min(z_values) if z_values else None,
        "zscore_max": max(z_values) if z_values else None,
        "forward_gross_returns_after_buy_strong": forward,
        "negative_controls": negative_controls,
        "interpretation": "DESCRIPTIVE_GROSS_ONLY_NOT_A_VALIDATED_EDGE",
    }


def run(input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    m1, digest = _load_m1(input_path)
    results = {
        timeframe: _timeframe_report(m1, timeframe, every)
        for timeframe, every in TIMEFRAMES.items()
    }
    report = {
        "schema_version": "qros-bnf-timeframe-diagnostics.v1",
        "source_dataset": str(input_path.relative_to(ROOT)),
        "source_sha256": digest,
        "m1_rows": m1.height,
        "timeframe_config": {
            "ma_window": 25,
            "historical_quantile_window": 500,
            "minimum_quantile_observations": 100,
            "strong_quantile": 0.01,
            "candidate_quantile": 0.05,
            "turnover_capacity_filter": "DISABLED_BY_DEFAULT_FOR_CFD_TICK_VOLUME",
            "costs_verified": False,
        },
        "results": results,
        "decision": "NO_EDGE_CLAIM_COSTS_AND_OUT_OF_SAMPLE_VALIDATION_REQUIRED",
        "execution_authorized": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps({
        "output": str(DEFAULT_OUTPUT),
        "source_sha256": result["source_sha256"],
        "timeframes": {
            key: {
                "bars": value["bars"],
                "BUY_STRONG": value["strong_signal_count"],
                "CANDIDATE": value["candidate_signal_count"],
                "NO_TRADE_fraction": value["no_trade_fraction"],
                "forward_1bar": value["forward_gross_returns_after_buy_strong"]["1"],
            }
            for key, value in result["results"].items()
        },
    }, indent=2))
