"""Recompute the 19-pair ledger with per-order-type slippage and report break-even allowances."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import polars as pl
import yaml

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "artifacts/qros_follow_19_costed_trade_rows_20261017.parquet"
COSTS = ROOT / "config/costs.yaml"
OUTPUT = ROOT / "artifacts/qros_follow_order_type_slippage_20261017.json"
PARQUET_OUT = ROOT / "artifacts/qros_follow_19_order_type_costed_trades_20261017.parquet"
MULTIPLIERS = (0.5, 1.0, 1.5, 2.0)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(frame: pl.DataFrame, costs: dict) -> dict:
    if frame.height == 0:
        return {"n": 0}
    result = {"n": frame.height}
    for name, expr in {
        "gross_mean": pl.col("gross_return").mean(),
        "spread_plus_commission_mean": pl.col("spread_plus_commission_net_return").mean(),
        "order_type_slippage_mean": pl.col("order_type_slippage_return").mean(),
        "net_mean": pl.col("order_type_net_return").mean(),
        "net_median": pl.col("order_type_net_return").median(),
        "net_win_rate": (pl.col("order_type_net_return") > 0).mean(),
        **{f"net_mean_x{multiplier:g}": pl.col(f"order_type_net_return_x{multiplier:g}").mean() for multiplier in MULTIPLIERS},
    }.items():
        result[name] = frame.select(expr.alias("v")).item()
    entry_prices = frame["entry_price_executable"].to_numpy()
    net_before = frame["spread_plus_commission_net_return"].to_numpy()
    gross_budget = float(np.sum(net_before * entry_prices))
    result["break_even_slippage_budget_price_units_per_trade_all_orders"] = float(
        np.mean(net_before * entry_prices)
    )
    order_counts = {"market_entry": frame.height}
    order_counts.update({name: frame.filter(pl.col("exit_order_type") == name).height for name in ("tp_limit", "sl_stop", "market_exit")})
    result["break_even_slippage_price_units_per_fill_if_only_this_order_type_has_slippage"] = {
        order_type: (gross_budget / count if count else None)
        for order_type, count in order_counts.items()
    }
    result["order_fill_counts"] = order_counts
    result["assumed_slippage_price_units_per_fill"] = {
        name: float(item["price_units_per_fill"]) for name, item in costs["slippage"]["order_types"].items()
    }
    return result


def run() -> dict:
    if not LEDGER.is_file():
        raise FileNotFoundError(f"Missing prior trade ledger: {LEDGER}")
    costs = yaml.safe_load(COSTS.read_text(encoding="utf-8"))
    if costs.get("schema_version") != "qros-xauusd-costs.v2":
        raise ValueError("ORDER_TYPE_COST_CONFIG_SCHEMA_INVALID")
    frame = pl.read_parquet(LEDGER)
    required = {
        "pair_id", "direction_mode", "exit_reason", "gross_return", "spread_plus_commission_net_return",
        "entry_price_executable", "holdout_flag", "execution_authorized",
    }
    if not required.issubset(frame.columns):
        raise ValueError(f"TRADE_LEDGER_COLUMNS_MISSING:{sorted(required - set(frame.columns))}")
    exit_type = pl.when(pl.col("exit_reason") == "TAKE_PROFIT").then(pl.lit("tp_limit")).when(
        pl.col("exit_reason") == "STOP_LOSS"
    ).then(pl.lit("sl_stop")).otherwise(pl.lit("market_exit"))
    frame = frame.with_columns(exit_type.alias("exit_order_type"))
    order_config = costs["slippage"]["order_types"]
    entry_slip = float(order_config["market_entry"]["price_units_per_fill"])
    exit_slip = (
        pl.when(pl.col("exit_order_type") == "tp_limit").then(pl.lit(float(order_config["tp_limit"]["price_units_per_fill"])))
        .when(pl.col("exit_order_type") == "sl_stop").then(pl.lit(float(order_config["sl_stop"]["price_units_per_fill"])))
        .otherwise(pl.lit(float(order_config["market_exit"]["price_units_per_fill"])))
    )
    frame = frame.with_columns(
        exit_slip.alias("exit_slippage_price_units"),
        (pl.lit(entry_slip) + exit_slip).alias("order_type_slippage_price_units"),
    ).with_columns(
        (pl.col("order_type_slippage_price_units") / pl.col("entry_price_executable")).alias("order_type_slippage_return")
    ).with_columns(
        (pl.col("spread_plus_commission_net_return") - pl.col("order_type_slippage_return")).alias("order_type_net_return")
    )
    for multiplier in MULTIPLIERS:
        frame = frame.with_columns(
            (pl.col("gross_return") - (pl.col("gross_return") - pl.col("spread_plus_commission_net_return")) * multiplier
             - pl.col("order_type_slippage_return") * multiplier).alias(f"order_type_net_return_x{multiplier:g}")
        )
    frame = frame.with_columns(pl.lit(False).alias("execution_authorized"))
    frame.write_parquet(PARQUET_OUT, compression="zstd")
    grouped = {}
    for mode in ("FOLLOW_SIGNAL", "REVERSE_SIGNAL"):
        sub = frame.filter(pl.col("direction_mode") == mode)
        grouped[mode] = {
            "all_period": summarize(sub, costs),
            "holdout_period": summarize(sub.filter(pl.col("holdout_flag")), costs),
            "by_exit_order_type": {
                order_type: summarize(sub.filter(pl.col("exit_order_type") == order_type), costs)
                for order_type in ("tp_limit", "sl_stop", "market_exit")
            },
        }
    report = {
        "schema_version": "qros-order-type-slippage-screen.v1",
        "input_parquet": str(LEDGER.relative_to(ROOT)),
        "input_parquet_sha256": sha256(LEDGER),
        "cost_config": str(COSTS.relative_to(ROOT)),
        "cost_config_sha256": sha256(COSTS),
        "slippage_model": costs["slippage"]["model"],
        "slippage_assumptions": costs["slippage"]["order_types"],
        "rows": frame.height,
        "results": grouped,
        "break_even_definition": "For each order class, sum per-trade pre-slippage net return multiplied by executable entry price across all included trades, divided by count of fills of that class; assumes all other slippage classes are zero. A negative result means no nonnegative adverse slippage allowance can break even under that allocation.",
        "costs_verified": False,
        "execution_authorized": False,
        "limitations": [
            "Existing ledger omits 1,451 rows with incomplete M1 exit spread; missingness bias is reported separately.",
            "Commission and each order-type slippage value remain assumptions, not observed broker fills.",
            "The historical selected period is not an untouched holdout.",
        ],
    }
    OUTPUT.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    manifest = ROOT / "artifacts/qros_follow_order_type_slippage_20261017.sha256"
    manifest.write_text(
        f"{sha256(PARQUET_OUT)}  {PARQUET_OUT.name}\n{sha256(OUTPUT)}  {OUTPUT.name}\n",
        encoding="ascii",
    )
    print(json.dumps({
        "report": str(OUTPUT.relative_to(ROOT)),
        "parquet": str(PARQUET_OUT.relative_to(ROOT)),
        "rows": frame.height,
        "results": {mode: {
            "holdout_n": grouped[mode]["holdout_period"]["n"],
            "holdout_net_mean": grouped[mode]["holdout_period"].get("net_mean"),
            "break_even_per_fill": grouped[mode]["holdout_period"].get("break_even_slippage_price_units_per_fill_if_only_this_order_type_has_slippage"),
        } for mode in grouped},
    }, indent=2))
    return report


if __name__ == "__main__":
    run()
