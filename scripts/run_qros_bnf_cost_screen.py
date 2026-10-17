"""Cost-first XAUUSD BNF diagnostics with bar-level spread and explicit assumptions.

This is a research sensitivity run, not a claim of broker-verified net performance.
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

import polars as pl

from researchos.orchestration.qros_research_controls import apply_bnf_mean_reversion
from researchos.orchestration.xauusd_cost_model import (
    calculate_trade_costs,
    cost_config_completeness,
    load_cost_config,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "mt5" / "xauusd" / "XAUUSD_M1_2021_2025_MT5.csv"
COST_CONFIG = ROOT / "config" / "costs.yaml"
MANIFEST = ROOT / "data" / "mt5" / "xauusd" / "XAUUSD_M1_2021_2025_MT5.manifest.json"
ARTIFACT_DIR = ROOT / "artifacts"
TRADE_OUTPUT = ARTIFACT_DIR / "qros_bnf_costed_trades_20261017.parquet"
REPORT_OUTPUT = ARTIFACT_DIR / "qros_bnf_cost_first_screen_20261017.json"
TIMEFRAMES = {"M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}
COST_MULTIPLIERS = (0.5, 1.0, 1.5, 2.0)
PERMUTATIONS = 1000


def load_m1(path: Path) -> tuple[pl.DataFrame, str]:
    raw = path.read_bytes()
    frame = pl.read_csv(path, try_parse_dates=False)
    frame = frame.rename({"time": "timestamp", "tick_volume": "volume"})
    frame = frame.with_columns(
        pl.col("timestamp").str.to_datetime(strict=True, time_zone="UTC"),
        *[pl.col(c).cast(pl.Float64) for c in ("open", "high", "low", "close", "volume", "spread")],
    ).sort("timestamp")
    if frame["timestamp"].n_unique() != frame.height:
        raise ValueError("DUPLICATE_M1_TIMESTAMPS")
    if frame["spread"].null_count() or (frame["spread"] < 0).any():
        raise ValueError("INVALID_SPREAD_LOG")
    return frame, hashlib.sha256(raw).hexdigest()


def timeframe_bars(m1: pl.DataFrame, every: str) -> pl.DataFrame:
    bars = m1.group_by_dynamic("timestamp", every=every, closed="left", label="left").agg([
        pl.col("open").first().alias("open"),
        pl.col("high").max().alias("high"),
        pl.col("low").min().alias("low"),
        pl.col("close").last().alias("close"),
        pl.col("volume").sum().alias("volume"),
        pl.col("spread").first().alias("spread_first"),
        pl.col("spread").last().alias("spread_last"),
    ]).drop_nulls("close").sort("timestamp")
    bars = bars.with_columns(
        pl.max_horizontal(
            pl.col("high") - pl.col("low"),
            (pl.col("high") - pl.col("close").shift(1)).abs(),
            (pl.col("low") - pl.col("close").shift(1)).abs(),
        ).alias("true_range")
    ).with_columns(
        pl.col("true_range").rolling_mean(window_size=14, min_samples=14).alias("atr14")
    )
    return bars


def make_trade(
    *, bars: pl.DataFrame, signal_index: int, horizon: int, timeframe: str,
    signal: str, config: dict[str, Any], dataset_sha256: str,
) -> dict[str, Any] | None:
    # Signal is known at close of signal bar; entry occurs at next bar open.
    entry_index = signal_index + 1
    exit_index = entry_index + horizon
    if exit_index >= bars.height:
        return None
    row_entry = bars.row(entry_index, named=True)
    row_exit = bars.row(exit_index, named=True)
    signal_row = bars.row(signal_index, named=True)
    atr_entry, atr_exit = row_entry["atr14"], row_exit["atr14"]
    if atr_entry is None or atr_exit is None or row_entry["open"] <= 0 or row_exit["close"] <= 0:
        return None
    direction = 1 if signal == "BUY_STRONG" else -1
    result = {
        "trade_id": hashlib.sha256(
            f"{dataset_sha256}|{timeframe}|{signal_index}|{horizon}|{signal}".encode()
        ).hexdigest(),
        "dataset_sha256": dataset_sha256,
        "timeframe": timeframe,
        "signal": signal,
        "signal_ts": signal_row["timestamp"],
        "entry_ts": row_entry["timestamp"],
        "exit_ts": row_exit["timestamp"],
        "horizon_bars": horizon,
        "direction": direction,
        "entry_price": float(row_entry["open"]),
        "exit_price": float(row_exit["close"]),
        "entry_spread": float(row_entry["spread_first"]),
        "exit_spread": float(row_exit["spread_last"]),
        "entry_atr": float(atr_entry),
        "exit_atr": float(atr_exit),
    }
    for multiplier in COST_MULTIPLIERS:
        costs = calculate_trade_costs(
            entry_price=result["entry_price"], exit_price=result["exit_price"],
            direction=direction, entry_spread_points=result["entry_spread"],
            exit_spread_points=result["exit_spread"], entry_atr=result["entry_atr"],
            exit_atr=result["exit_atr"], config=config, cost_multiplier=multiplier,
        )
        for key in ("gross_return", "spread_cost_return", "commission_cost_return",
                    "slippage_cost_return", "total_cost_return", "net_return",
                    "cost_basis_declared", "costs_verified", "cost_assumptions"):
            result[f"{key}_x{multiplier:g}"] = costs.get(key)
    return result


def permutation_test(
    observed: list[float], null_population: list[float], *, seed: int, repetitions: int = PERMUTATIONS,
) -> dict[str, Any]:
    if not observed or len(null_population) < len(observed):
        return {"status": "INSUFFICIENT_SAMPLE", "p_value": None, "repetitions": repetitions}
    rng = random.Random(seed)
    observed_mean = sum(observed) / len(observed)
    null_means = [
        sum(rng.sample(null_population, len(observed))) / len(observed)
        for _ in range(repetitions)
    ]
    p_value = (1 + sum(value >= observed_mean for value in null_means)) / (repetitions + 1)
    return {
        "status": "COMPUTED_SENSITIVITY_P_VALUE",
        "observed_mean_net_return": observed_mean,
        "null_mean": sum(null_means) / len(null_means),
        "p_value": p_value,
        "repetitions": repetitions,
        "seed": seed,
        "method": "ONE_SIDED_RANDOM_ENTRY_PERMUTATION",
        "interpretation": "ASSUMPTION_DEPENDENT_RESEARCH_DIAGNOSTIC_NOT_VERIFIED_EDGE",
    }


def run() -> dict[str, Any]:
    m1, dataset_sha = load_m1(SOURCE)
    config = load_cost_config(COST_CONFIG)
    completeness = cost_config_completeness(config)
    all_trades: list[dict[str, Any]] = []
    results: dict[str, Any] = {}
    for timeframe, every in TIMEFRAMES.items():
        bars = timeframe_bars(m1, every)
        signals = apply_bnf_mean_reversion(
            bars.select("timestamp", "close", "volume"),
            window_size=25, quantile_window=500, quantile_min_samples=100,
            strong_quantile=0.01, candidate_quantile=0.05,
        )
        signal_labels = signals["bnf_signal"].to_list()
        signal_rows = [
            make_trade(bars=bars, signal_index=i, horizon=h, timeframe=timeframe,
                       signal=label, config=config, dataset_sha256=dataset_sha)
            for i, label in enumerate(signal_labels)
            if label == "BUY_STRONG"
            for h in (1, 3, 5)
        ]
        rows = [row for row in signal_rows if row is not None]
        all_trades.extend(rows)
        strong_one = [row for row in rows if row["horizon_bars"] == 1]
        candidate_one = [
            label for i, label in enumerate(signal_labels)
            if label == "CANDIDATE" and i + 2 < bars.height
            and bars["atr14"][i + 1] is not None and bars["atr14"][i + 2] is not None
        ]
        # Build matched null population using every eligible bar, not just signal bars.
        eligible_idx = [
            i for i in range(25, max(25, bars.height - 6))
            if signal_labels[i] in {"BUY_STRONG", "CANDIDATE", "NO_TRADE"}
        ]
        null_rows = [
            make_trade(bars=bars, signal_index=i, horizon=1, timeframe=timeframe,
                       signal="BUY_STRONG", config=config, dataset_sha256=dataset_sha)
            for i in eligible_idx
        ]
        null_rows = [row for row in null_rows if row is not None]
        observed_returns = [row["net_return_x1"] for row in strong_one if isinstance(row["net_return_x1"], (int, float))]
        null_returns = [row["net_return_x1"] for row in null_rows if isinstance(row["net_return_x1"], (int, float))]
        sensitivity: dict[str, Any] = {}
        for multiplier in COST_MULTIPLIERS:
            key = f"net_return_x{multiplier:g}"
            vals = [float(row[key]) for row in strong_one if isinstance(row.get(key), (int, float))]
            sensitivity[f"{multiplier:g}x"] = {
                "n": len(vals),
                "mean_net_return_under_declared_model": sum(vals) / len(vals) if vals else None,
                "positive_fraction": sum(value > 0 for value in vals) / len(vals) if vals else None,
                "decision": "INSUFFICIENT_SAMPLE" if len(vals) < 100 else (
                    "REJECTED_COST_FRAGILE" if sum(vals) / len(vals) <= 0 and multiplier >= 1.5 else "SENSITIVITY_ONLY"
                ),
            }
        permutation_seed = 20261017 + {"M15": 15, "H1": 60, "H4": 240, "D1": 1440}[timeframe]
        random_entry_test = permutation_test(
            observed_returns, null_returns, seed=permutation_seed
        )
        shuffled_signal_test = permutation_test(
            observed_returns, null_returns, seed=permutation_seed + 100_000
        )
        results[timeframe] = {
            "bars": bars.height,
            "buy_strong_trade_count_h1": len(strong_one),
            "candidate_trade_count_h1": len(candidate_one),
            "min_sample_size_for_screen": 100,
            "cost_config_complete": completeness["cost_basis_declared"],
            "costs_verified": completeness["costs_verified"],
            "cost_assumptions": completeness["assumption_fields"],
            "cost_multiplier_screen": sensitivity,
            "random_entry_permutation": random_entry_test,
            "shuffled_signal_permutation": shuffled_signal_test,
            "d1_or_small_sample_warning": "INSUFFICIENT_SAMPLE" if len(strong_one) < 100 else None,
            "execution_authorized": False,
        }
    trial_registry: list[dict[str, Any]] = []
    for timeframe, result in results.items():
        for trial_kind in ("random_entry_permutation", "shuffled_signal_permutation"):
            test_result = result[trial_kind]
            p_value = test_result.get("p_value")
            trial = {
                "trial_id": f"bnf_{timeframe.lower()}_{trial_kind}",
                "timeframe": timeframe,
                "trial_kind": trial_kind,
                "dataset_sha256": dataset_sha,
                "cost_config_sha256": hashlib.sha256(COST_CONFIG.read_bytes()).hexdigest(),
                "p_value": p_value,
                "p_value_source": "1000_REPETITION_PERMUTATION" if p_value is not None else "UNAVAILABLE",
            }
            trial["trial_sha256"] = hashlib.sha256(
                json.dumps(trial, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
            ).hexdigest()
            trial_registry.append(trial)
    valid_trials = [trial for trial in trial_registry if isinstance(trial["p_value"], (int, float))]
    ordered = sorted(valid_trials, key=lambda item: float(item["p_value"]))
    total = len(ordered)
    running_q = 1.0
    for rank in range(total, 0, -1):
        trial = ordered[rank - 1]
        running_q = min(running_q, float(trial["p_value"]) * total / rank)
        trial["bh_adjusted_p_value"] = min(1.0, running_q)
    for trial in trial_registry:
        trial.setdefault("bh_adjusted_p_value", None)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(all_trades).write_parquet(TRADE_OUTPUT, compression="zstd")
    report = {
        "schema_version": "qros-bnf-cost-first-screen.v1",
        "dataset": str(SOURCE.relative_to(ROOT)),
        "dataset_sha256": dataset_sha,
        "dataset_period": "2021-01-04 through 2025-12-31; 2026 OOS data not present in this frozen file",
        "cost_config_sha256": hashlib.sha256(COST_CONFIG.read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "symbol_metadata": {
            "point": config["symbol_point"]["value"], "digits": config["digits"]["value"],
            "contract_size": config["contract_size"]["value"],
        },
        "cost_config_completeness": completeness,
        "commission_assumption_usd_per_lot_round_turn": config["commission"]["round_turn_usd_per_lot"]["value"],
        "slippage_model": config["slippage"]["model"],
        "slippage_assumptions_by_order_type": config["slippage"]["order_types"],
        "spread_application": "ENTRY_BAR_FIRST_SPREAD_AND_EXIT_BAR_LAST_SPREAD; NO MEDIAN SUBSTITUTION",
        "cost_multipliers": list(COST_MULTIPLIERS),
        "permutations": PERMUTATIONS,
        "results": results,
        "trial_registry": trial_registry,
        "multiple_testing": {
            "method": "BENJAMINI_HOCHBERG",
            "family_size": len(valid_trials),
            "p_values_available": len(valid_trials),
            "interpretation": "Only the registered permutation tests in this artifact are included; this is not a registry of all historical QROS trials.",
        },
        "trade_parquet": str(TRADE_OUTPUT.relative_to(ROOT)),
        "trade_rows": len(all_trades),
        "decision": "MODELED_COST_SENSITIVITY_ONLY; ASSUMED COMMISSION/SLIPPAGE ARE NOT VERIFIED",
        "execution_authorized": False,
    }
    REPORT_OUTPUT.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
