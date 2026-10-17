"""XAUUSD cost conversion and cost-first trade accounting.

Modeled costs are never promoted to measured/verified execution costs.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import polars as pl
import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COSTS = ROOT / "config" / "costs.yaml"
MANIFEST = ROOT / "data" / "mt5" / "xauusd" / "XAUUSD_M1_2021_2025_MT5.manifest.json"


def load_cost_config(path: Path = DEFAULT_COSTS) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("schema_version") != "qros-xauusd-costs.v2":
        raise ValueError("INVALID_COST_CONFIG_SCHEMA")
    metadata = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual_manifest_sha = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    source = config.get("metadata_source", {})
    if source.get("sha256") != actual_manifest_sha:
        raise ValueError("COST_METADATA_MANIFEST_HASH_MISMATCH")
    quote_basis = config.get("quote_basis", {})
    if quote_basis.get("source") != "measured" or quote_basis.get("value") != "bid":
        raise ValueError("COST_QUOTE_BASIS_MUST_DECLARE_MT5_BID_OHLC")
    measured = metadata.get("symbol_metadata", {})
    for key, manifest_key in (("symbol_point", "point"), ("digits", "digits"), ("contract_size", "trade_contract_size")):
        field = config.get(key, {})
        if field.get("source") not in {"measured", "assumed"} or field.get("value") != measured.get(manifest_key):
            raise ValueError(f"COST_{key.upper()}_DOES_NOT_MATCH_MANIFEST")
    return config


def mt5_spread_points_to_price(spread_points: float, symbol_point: float) -> float:
    values = (spread_points, symbol_point)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) for v in values):
        raise ValueError("SPREAD_AND_POINT_MUST_BE_FINITE_NUMBERS")
    if spread_points < 0 or symbol_point <= 0:
        raise ValueError("SPREAD_MUST_BE_NONNEGATIVE_AND_POINT_POSITIVE")
    return float(spread_points) * float(symbol_point)


def cost_config_completeness(config: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    commission = config.get("commission", {}).get("round_turn_usd_per_lot", {})
    order_slippage = config.get("slippage", {}).get("order_types", {})
    for name, field in (("commission", commission),):
        value = field.get("value")
        source = field.get("source")
        if source not in {"measured", "assumed"}:
            failures.append(f"{name.upper()}_SOURCE_INVALID")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            failures.append(f"{name.upper()}_VALUE_MISSING")
        elif value < 0:
            failures.append(f"{name.upper()}_VALUE_NEGATIVE")
        elif value == 0 and source == "assumed":
            failures.append(f"{name.upper()}_ASSUMED_ZERO_FORBIDDEN")
    required_order_types = ("market_entry", "tp_limit", "sl_stop", "market_exit")
    for order_type in required_order_types:
        field = order_slippage.get(order_type, {})
        value = field.get("price_units_per_fill")
        source = field.get("source")
        if source not in {"measured", "assumed"}:
            failures.append(f"SLIPPAGE_{order_type.upper()}_SOURCE_INVALID")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            failures.append(f"SLIPPAGE_{order_type.upper()}_VALUE_MISSING")
        elif value < 0:
            failures.append(f"SLIPPAGE_{order_type.upper()}_VALUE_NEGATIVE")
        elif value == 0 and source == "assumed":
            failures.append(f"SLIPPAGE_{order_type.upper()}_ASSUMED_ZERO_FORBIDDEN")
    if config.get("spread", {}).get("raw_unit") != "MT5_points":
        failures.append("SPREAD_UNIT_UNDECLARED")
    return {
        "cost_basis_declared": not failures,
        "costs_verified": (
            not failures
            and commission.get("source") == "measured"
            and all(order_slippage.get(name, {}).get("source") == "measured" for name in required_order_types)
        ),
        "failures": failures,
        "assumption_fields": [
            *([ "commission" ] if commission.get("source") == "assumed" else []),
            *[
                f"slippage.{order_type}"
                for order_type, field in order_slippage.items()
                if isinstance(field, dict) and field.get("source") == "assumed"
            ],
        ],
    }


def calculate_trade_costs(
    *,
    entry_price: float,
    exit_price: float,
    direction: int,
    entry_spread_points: float,
    exit_spread_points: float,
    entry_atr: float,
    exit_atr: float,
    config: dict[str, Any],
    cost_multiplier: float = 1.0,
    exit_reason: str = "TIMEOUT",
) -> dict[str, Any]:
    """Return auditable costs and net return under declared model parameters."""
    numbers = {
        "entry_price": entry_price, "exit_price": exit_price,
        "entry_atr": entry_atr, "exit_atr": exit_atr, "cost_multiplier": cost_multiplier,
    }
    for name, value in numbers.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"INVALID_{name.upper()}")
    if entry_price <= 0 or exit_price <= 0 or direction not in {-1, 1} or cost_multiplier <= 0:
        raise ValueError("INVALID_TRADE_PARAMETERS")
    completeness = cost_config_completeness(config)
    if not completeness["cost_basis_declared"]:
        return {
            "cost_basis_declared": False, "costs_verified": False,
            "net_return": None, "cost_failures": completeness["failures"],
            "execution_authorized": False,
        }
    point = float(config["symbol_point"]["value"])
    contract = float(config["contract_size"]["value"])
    commission = float(config["commission"]["round_turn_usd_per_lot"]["value"])
    exit_order_type = {
        "TAKE_PROFIT": "tp_limit",
        "STOP_LOSS": "sl_stop",
        "TIMEOUT": "market_exit",
    }.get(exit_reason)
    if exit_order_type is None:
        raise ValueError(f"INVALID_EXIT_REASON:{exit_reason}")
    order_slippage = config["slippage"]["order_types"]
    entry_slippage_price = float(order_slippage["market_entry"]["price_units_per_fill"])
    exit_slippage_price = float(order_slippage[exit_order_type]["price_units_per_fill"])
    spread_entry_price = mt5_spread_points_to_price(entry_spread_points, point)
    spread_exit_price = mt5_spread_points_to_price(exit_spread_points, point)
    # MT5 historical OHLC is bid-side. A long enters at ask and exits at bid;
    # a short enters at bid and exits at ask. Apply one executable-side spread,
    # not half-spread at both legs and not a double-counted round turn.
    gross_return = direction * (exit_price / entry_price - 1.0)
    if direction == 1:
        executable_return = exit_price / (entry_price + spread_entry_price) - 1.0
        spread_return = gross_return - executable_return
        executable_entry_price = entry_price + spread_entry_price
    else:
        executable_return = 1.0 - (exit_price + spread_exit_price) / entry_price
        spread_return = gross_return - executable_return
        executable_entry_price = entry_price
    # Order-type adverse fill assumptions are explicit price units per fill.
    # They are not ATR-scaled and remain unverified until backed by broker fills.
    slippage_cost_price = entry_slippage_price + exit_slippage_price
    commission_return = commission / (contract * executable_entry_price)
    slippage_return = slippage_cost_price / executable_entry_price
    spread_cost_price = spread_return * entry_price
    total_cost_return = cost_multiplier * (spread_return + slippage_return + commission_return)
    return {
        "cost_basis_declared": True,
        "costs_verified": completeness["costs_verified"],
        "cost_assumptions": completeness["assumption_fields"],
        "gross_return": gross_return,
        "entry_spread_points": float(entry_spread_points),
        "exit_spread_points": float(exit_spread_points),
        "spread_cost_price": spread_cost_price * cost_multiplier,
        "entry_executable_price": entry_price + spread_entry_price if direction == 1 else entry_price,
        "exit_executable_price": exit_price if direction == 1 else exit_price + spread_exit_price,
        "spread_accounting": "LONG_ENTRY_ASK_EXIT_BID" if direction == 1 else "SHORT_ENTRY_BID_EXIT_ASK",
        "spread_cost_return": spread_return * cost_multiplier,
        "commission_usd_per_lot_round_turn": commission * cost_multiplier,
        "commission_cost_return": commission_return * cost_multiplier,
        "slippage_entry_order_type": "market_entry",
        "slippage_exit_order_type": exit_order_type,
        "slippage_entry_price_units": entry_slippage_price * cost_multiplier,
        "slippage_exit_price_units": exit_slippage_price * cost_multiplier,
        "slippage_cost_price": slippage_cost_price * cost_multiplier,
        "slippage_cost_return": slippage_return * cost_multiplier,
        "total_cost_return": total_cost_return,
        "net_return": gross_return - total_cost_return,
        "cost_multiplier": cost_multiplier,
        "execution_authorized": False,
    }


def append_trade_costs(trades: pl.DataFrame, config: dict[str, Any], multiplier: float = 1.0) -> pl.DataFrame:
    required = {
        "entry_ts", "exit_ts", "entry_price", "exit_price", "direction",
        "entry_spread", "exit_spread", "entry_atr", "exit_atr",
    }
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"TRADE_COLUMNS_MISSING:{sorted(missing)}")
    rows = [
        calculate_trade_costs(
            entry_price=row["entry_price"], exit_price=row["exit_price"],
            direction=row["direction"], entry_spread_points=row["entry_spread"],
            exit_spread_points=row["exit_spread"], entry_atr=row["entry_atr"],
            exit_atr=row["exit_atr"], config=config, cost_multiplier=multiplier,
            exit_reason=row.get("exit_reason", "TIMEOUT"),
        )
        for row in trades.iter_rows(named=True)
    ]
    cost_frame = pl.DataFrame(rows) if rows else pl.DataFrame()
    return pl.concat([trades, cost_frame], how="horizontal") if rows else trades


__all__ = [
    "load_cost_config", "cost_config_completeness", "mt5_spread_points_to_price",
    "calculate_trade_costs", "append_trade_costs",
]
