from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import polars as pl

QROS_RESEARCH_CONTROLS_VERSION = "QROS_RESEARCH_CONTROLS_V1"


def _finite(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"INVALID_{name.upper()}")
    return float(value)


def calculate_quarter_kelly_size(*, win_probability: float, average_win: float, average_loss: float,
                                  cost_per_unit: float, equity: float, entry_price: float,
                                  stop_loss_price: float, contract_multiplier: float,
                                  risk_limit_fraction: float = 0.02,
                                  fractional_kelly: float = 0.25) -> dict[str, Any]:
    """Research-only binary-payoff Kelly sizing; returns NO_TRADE on non-positive edge.

    average_win/loss and cost_per_unit are in account currency per one unit.
    contract_multiplier converts price distance to account-currency loss per unit.
    """
    values = {k: _finite(k, v) for k, v in {
        "win_probability": win_probability, "average_win": average_win, "average_loss": average_loss,
        "cost_per_unit": cost_per_unit, "equity": equity, "entry_price": entry_price,
        "stop_loss_price": stop_loss_price, "contract_multiplier": contract_multiplier,
        "risk_limit_fraction": risk_limit_fraction, "fractional_kelly": fractional_kelly,
    }.items()}
    p, w, loss, cost = values["win_probability"], values["average_win"], values["average_loss"], values["cost_per_unit"]
    if not 0 <= p <= 1 or w <= 0 or loss <= 0 or cost < 0 or values["equity"] <= 0:
        raise ValueError("INVALID_PAYOFF_OR_EQUITY")
    if values["entry_price"] <= 0 or values["stop_loss_price"] <= 0 or values["entry_price"] == values["stop_loss_price"]:
        raise ValueError("INVALID_ENTRY_OR_STOP")
    if values["contract_multiplier"] <= 0 or not 0 < values["risk_limit_fraction"] <= 0.02:
        raise ValueError("INVALID_CONTRACT_MULTIPLIER_OR_RISK_LIMIT")
    if not 0 < values["fractional_kelly"] <= 1:
        raise ValueError("INVALID_FRACTIONAL_KELLY")

    net_ev = p * w - (1.0 - p) * loss - cost
    stop_risk_per_unit = abs(values["entry_price"] - values["stop_loss_price"]) * values["contract_multiplier"] + cost
    if not math.isfinite(net_ev) or not math.isfinite(stop_risk_per_unit) or stop_risk_per_unit <= 0:
        raise ValueError("NONFINITE_EXPECTANCY_OR_STOP_RISK")
    if net_ev <= 0:
        return {"version": QROS_RESEARCH_CONTROLS_VERSION, "status": "NO_TRADE", "reason": "NON_POSITIVE_NET_EXPECTANCY",
                "net_expectancy": net_ev, "full_kelly_fraction": 0.0, "quarter_kelly_fraction": 0.0,
                "risk_budget": 0.0, "position_size": 0.0, "execution_authorized": False}

    # Standard binary Kelly fraction from the net win/loss payoff ratio.
    win_net, loss_net = w - cost, loss + cost
    if win_net <= 0:
        return {"version": QROS_RESEARCH_CONTROLS_VERSION, "status": "NO_TRADE", "reason": "COSTS_ERASE_WIN_PAYOFF",
                "net_expectancy": net_ev, "full_kelly_fraction": 0.0, "quarter_kelly_fraction": 0.0,
                "risk_budget": 0.0, "position_size": 0.0, "execution_authorized": False}
    payoff_ratio = win_net / loss_net
    full_kelly = max(0.0, p - (1.0 - p) / payoff_ratio)
    quarter_kelly = full_kelly * values["fractional_kelly"]
    final_fraction = min(quarter_kelly, values["risk_limit_fraction"])
    risk_budget = values["equity"] * final_fraction
    position_size = risk_budget / stop_risk_per_unit
    return {"version": QROS_RESEARCH_CONTROLS_VERSION, "status": "CANDIDATE_FOR_RESEARCH_REVIEW",
            "reason": "POSITIVE_NET_EXPECTANCY_WITHIN_RISK_CAP", "net_expectancy": net_ev,
            "full_kelly_fraction": full_kelly, "quarter_kelly_fraction": quarter_kelly,
            "final_risk_fraction": final_fraction, "risk_budget": risk_budget,
            "stop_risk_per_unit": stop_risk_per_unit, "position_size": position_size,
            "execution_authorized": False}


def apply_bnf_mean_reversion(df: pl.DataFrame, *, capacity_cap: float = 15_000_000_000.0,
                             window_size: int = 25, strong_deviation: float = -0.35,
                             candidate_deviation: float = -0.20) -> pl.DataFrame:
    """Add MA/deviation/BNF candidate columns; never emits executable instructions."""
    if not isinstance(df, pl.DataFrame):
        raise ValueError("INPUT_MUST_BE_POLARS_DATAFRAME")
    required = {"close", "volume"}
    if not required.issubset(df.columns):
        raise ValueError("MISSING_CLOSE_OR_VOLUME_COLUMN")
    if isinstance(window_size, bool) or not isinstance(window_size, int) or window_size < 2:
        raise ValueError("WINDOW_SIZE_MUST_BE_AT_LEAST_2")
    cap = _finite("capacity_cap", capacity_cap)
    strong = _finite("strong_deviation", strong_deviation)
    candidate = _finite("candidate_deviation", candidate_deviation)
    if cap <= 0 or not strong < candidate < 0:
        raise ValueError("INVALID_BNF_THRESHOLDS_OR_CAPACITY")
    if "timestamp" in df.columns:
        if not df["timestamp"].is_sorted():
            raise ValueError("TIMESTAMP_MUST_BE_SORTED_ASCENDING")
        if df["timestamp"].n_unique() != df.height:
            raise ValueError("DUPLICATE_TIMESTAMPS_NOT_ALLOWED")
    out = df.with_columns([
        pl.col("close").cast(pl.Float64).rolling_mean(window_size=window_size, min_samples=window_size).alias("ma_25" if window_size == 25 else f"ma_{window_size}"),
        (pl.col("volume").cast(pl.Float64) * pl.col("close").cast(pl.Float64)).alias("turnover"),
    ])
    ma_col = "ma_25" if window_size == 25 else f"ma_{window_size}"
    out = out.with_columns(((pl.col("close").cast(pl.Float64) - pl.col(ma_col)) / pl.col(ma_col)).alias("deviation"))
    valid = (pl.col("close").is_finite() & (pl.col("close") > 0) & pl.col(ma_col).is_finite() & (pl.col(ma_col) > 0) & pl.col("volume").is_finite() & (pl.col("volume") >= 0) & pl.col("turnover").is_finite()).fill_null(False)
    return out.with_columns([
        pl.when(~valid | pl.col("deviation").is_null()).then(pl.lit("NO_TRADE"))
        .when((pl.col("deviation") <= strong) & (pl.col("turnover") <= cap)).then(pl.lit("BUY_STRONG"))
        .when(pl.col("deviation") <= candidate).then(pl.lit("CANDIDATE"))
        .otherwise(pl.lit("NO_TRADE")).alias("bnf_signal"),
        pl.lit("RESEARCH_ONLY_NOT_EXECUTION").alias("decision_use"),
    ])


def unified_research_gate(*, net_expectancy: float, bootstrap_ci_lower: float,
                          robustness_score: float, fdr_passed: bool, costs_verified: bool,
                          minimum_sample_passed: bool, point_in_time_data_passed: bool,
                          risk_sizing_status: str, bnf_signal: str = "NO_TRADE",
                          insider_cluster: bool = False) -> dict[str, Any]:
    """Fail-closed synthesis; insider/BNF features never override statistical failures."""
    numeric = {k: _finite(k, v) for k, v in {"net_expectancy": net_expectancy,
               "bootstrap_ci_lower": bootstrap_ci_lower, "robustness_score": robustness_score}.items()}
    checks = {
        "positive_net_expectancy": numeric["net_expectancy"] > 0,
        "bootstrap_ci_lower_positive": numeric["bootstrap_ci_lower"] > 0,
        "robustness_score_at_least_0_90": 0.90 <= numeric["robustness_score"] <= 1.0,
        "fdr_passed": fdr_passed is True,
        "costs_verified": costs_verified is True,
        "minimum_sample_passed": minimum_sample_passed is True,
        "point_in_time_data_passed": point_in_time_data_passed is True,
        "risk_sizing_candidate": risk_sizing_status == "CANDIDATE_FOR_RESEARCH_REVIEW",
        "bnf_is_candidate": bnf_signal in {"BUY_STRONG", "CANDIDATE"},
    }
    status = "CANDIDATE_FOR_FURTHER_REVIEW" if all(checks.values()) else "NO_TRADE"
    return {"version": QROS_RESEARCH_CONTROLS_VERSION, "status": status, "checks": checks,
            "failed_checks": [k for k, v in checks.items() if not v],
            "insider_cluster_observed": insider_cluster,
            "insider_cluster_changes_gate": False,
            "execution_authorized": False, "decision_use": "RESEARCH_ONLY"}


def build_audit_record(*, input_payload: dict[str, Any], decision: dict[str, Any],
                       source_commit: str, config_version: str) -> dict[str, Any]:
    """Build deterministic provenance record with canonical SHA-256 hashes."""
    if not source_commit or not config_version:
        raise ValueError("SOURCE_COMMIT_AND_CONFIG_VERSION_REQUIRED")
    canonical_input = json.dumps(input_payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    canonical_decision = json.dumps(decision, sort_keys=True, separators=(",", ":"), allow_nan=False)
    input_hash = hashlib.sha256(canonical_input.encode("utf-8")).hexdigest()
    decision_hash = hashlib.sha256(canonical_decision.encode("utf-8")).hexdigest()
    return {"version": QROS_RESEARCH_CONTROLS_VERSION, "source_commit": source_commit,
            "config_version": config_version, "input_sha256": input_hash,
            "decision_sha256": decision_hash, "decision": decision,
            "execution_authorized": False}
