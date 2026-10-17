"""Fail-closed research controls using observed trade returns, not caller assertions.

All outputs are research-only. This module never authorizes execution.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping, Sequence
from typing import Any

import polars as pl

QROS_RESEARCH_CONTROLS_VERSION = "QROS_RESEARCH_CONTROLS_V2"
LEGACY_GATE_STATUS = "NO_TRADE_LEGACY_GATE_DISABLED"


def _finite(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"INVALID_{name.upper()}")
    return float(value)


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("EMPTY_BOOTSTRAP")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def _validate_return_series(values: Sequence[float], name: str, minimum: int = 2) -> list[float]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{name.upper()}_MUST_BE_A_SEQUENCE")
    result = [_finite(name, value) for value in values]
    if len(result) < minimum:
        raise ValueError(f"{name.upper()}_TOO_SHORT")
    return result


def _block_bootstrap_evidence(
    returns: Sequence[float], *, repetitions: int, seed: int, block_length: int | None = None
) -> dict[str, Any]:
    """Moving-block percentile CI and one-sided centered-null p-value for the mean."""
    values = list(returns)
    n = len(values)
    block = block_length if block_length is not None else max(2, round(n ** (1.0 / 3.0)))
    if isinstance(block, bool) or not isinstance(block, int) or not 1 <= block <= n:
        raise ValueError("INVALID_BLOCK_LENGTH")
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 999:
        raise ValueError("BOOTSTRAP_REPETITIONS_MUST_BE_AT_LEAST_999")
    mean = math.fsum(values) / n
    rng = random.Random(seed)
    starts = list(range(n - block + 1))
    needed = math.ceil(n / block)
    raw_means: list[float] = []
    null_means: list[float] = []
    centered = [value - mean for value in values]
    for _ in range(repetitions):
        sample: list[float] = []
        null_sample: list[float] = []
        for _ in range(needed):
            start = rng.choice(starts)
            sample.extend(values[start : start + block])
            null_sample.extend(centered[start : start + block])
        raw_means.append(math.fsum(sample[:n]) / n)
        null_means.append(math.fsum(null_sample[:n]) / n)
    alpha = 0.05
    p_value = (1 + sum(value >= mean for value in null_means)) / (repetitions + 1)
    return {
        "mean_net_return": mean,
        "ci_95_lower": _quantile(raw_means, alpha / 2),
        "ci_95_upper": _quantile(raw_means, 1.0 - alpha / 2),
        "one_sided_p_value": p_value,
        "block_length": block,
        "bootstrap_repetitions": repetitions,
        "bootstrap_seed": seed,
        "bootstrap_method": "MOVING_BLOCK_PERCENTILE_CI_AND_CENTERED_NULL",
    }


def _validate_cost_metadata(metadata: Mapping[str, Any] | None, observation_count: int) -> tuple[bool, list[str]]:
    """Validate provenance structure; this cannot independently prove vendor truth."""
    if not isinstance(metadata, Mapping):
        return False, ["COST_METADATA_MISSING"]
    required_text = ("cost_source", "cost_units", "commission_model", "slippage_model")
    failures = [f"COST_{key.upper()}_MISSING" for key in required_text if not isinstance(metadata.get(key), str) or not metadata[key].strip()]
    digest = metadata.get("spread_log_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdefABCDEF" for char in digest):
        failures.append("COST_SPREAD_LOG_HASH_INVALID")
    count = metadata.get("spread_observation_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < observation_count:
        failures.append("COST_SPREAD_LOG_COVERAGE_INSUFFICIENT")
    if metadata.get("net_return_definition") != "NET_OF_SPREAD_COMMISSION_SLIPPAGE":
        failures.append("COST_NET_RETURN_BASIS_UNDECLARED")
    return not failures, failures


def calculate_quarter_kelly_size(
    *, win_probability: float, average_win: float, average_loss: float,
    cost_per_unit: float, equity: float, entry_price: float,
    stop_loss_price: float, contract_multiplier: float,
    risk_limit_fraction: float = 0.02, fractional_kelly: float = 0.25,
) -> dict[str, Any]:
    """Research-only sizing diagnostic. It is not a validated edge or an order."""
    values = {k: _finite(k, v) for k, v in {
        "win_probability": win_probability, "average_win": average_win, "average_loss": average_loss,
        "cost_per_unit": cost_per_unit, "equity": equity, "entry_price": entry_price,
        "stop_loss_price": stop_loss_price, "contract_multiplier": contract_multiplier,
        "risk_limit_fraction": risk_limit_fraction, "fractional_kelly": fractional_kelly,
    }.items()}
    p, win, loss, cost = values["win_probability"], values["average_win"], values["average_loss"], values["cost_per_unit"]
    if not 0 <= p <= 1 or win <= 0 or loss <= 0 or cost < 0 or values["equity"] <= 0:
        raise ValueError("INVALID_PAYOFF_OR_EQUITY")
    if values["entry_price"] <= 0 or values["stop_loss_price"] <= 0 or values["entry_price"] == values["stop_loss_price"]:
        raise ValueError("INVALID_ENTRY_OR_STOP")
    if values["contract_multiplier"] <= 0 or not 0 < values["risk_limit_fraction"] <= 0.02:
        raise ValueError("INVALID_CONTRACT_MULTIPLIER_OR_RISK_LIMIT")
    if not 0 < values["fractional_kelly"] <= 1:
        raise ValueError("INVALID_FRACTIONAL_KELLY")
    net_ev = p * win - (1.0 - p) * loss - cost
    stop_risk = abs(values["entry_price"] - values["stop_loss_price"]) * values["contract_multiplier"] + cost
    if not math.isfinite(net_ev) or not math.isfinite(stop_risk) or stop_risk <= 0:
        raise ValueError("NONFINITE_EXPECTANCY_OR_STOP_RISK")
    if net_ev <= 0:
        return {"version": QROS_RESEARCH_CONTROLS_VERSION, "status": "NO_TRADE",
                "reason": "NON_POSITIVE_NET_EXPECTANCY", "net_expectancy": net_ev,
                "full_kelly_fraction": 0.0, "quarter_kelly_fraction": 0.0,
                "risk_budget": 0.0, "position_size": 0.0, "execution_authorized": False}
    win_net, loss_net = win - cost, loss + cost
    if win_net <= 0:
        return {"version": QROS_RESEARCH_CONTROLS_VERSION, "status": "NO_TRADE",
                "reason": "COSTS_ERASE_WIN_PAYOFF", "net_expectancy": net_ev,
                "full_kelly_fraction": 0.0, "quarter_kelly_fraction": 0.0,
                "risk_budget": 0.0, "position_size": 0.0, "execution_authorized": False}
    payoff_ratio = win_net / loss_net
    full_kelly = max(0.0, p - (1.0 - p) / payoff_ratio)
    quarter_kelly = full_kelly * values["fractional_kelly"]
    fraction = min(quarter_kelly, values["risk_limit_fraction"])
    risk_budget = values["equity"] * fraction
    return {"version": QROS_RESEARCH_CONTROLS_VERSION, "status": "CANDIDATE_FOR_RESEARCH_REVIEW",
            "reason": "POSITIVE_POINT_EXPECTANCY_ONLY_NOT_EDGE_VALIDATION", "net_expectancy": net_ev,
            "full_kelly_fraction": full_kelly, "quarter_kelly_fraction": quarter_kelly,
            "final_risk_fraction": fraction, "risk_budget": risk_budget,
            "stop_risk_per_unit": stop_risk, "position_size": risk_budget / stop_risk,
            "execution_authorized": False}


def apply_bnf_mean_reversion(
    df: pl.DataFrame, *, window_size: int = 25, quantile_window: int = 1000,
    quantile_min_samples: int = 200, strong_quantile: float = 0.01,
    candidate_quantile: float = 0.05, capacity_cap: float | None = None,
) -> pl.DataFrame:
    """Causal volatility-normalized XAUUSD deviation; thresholds use prior observations only.

    If capacity_cap is supplied, turnover=close*volume is applied as a separate optional
    filter. Leave it unset for CFD tick-volume feeds, where that proxy is not economic volume.
    """
    if not isinstance(df, pl.DataFrame):
        raise ValueError("INPUT_MUST_BE_POLARS_DATAFRAME")
    if "close" not in df.columns:
        raise ValueError("MISSING_CLOSE_COLUMN")
    for name, value in (("window_size", window_size), ("quantile_window", quantile_window), ("quantile_min_samples", quantile_min_samples)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 2:
            raise ValueError(f"{name.upper()}_MUST_BE_AT_LEAST_2")
    strong_q = _finite("strong_quantile", strong_quantile)
    candidate_q = _finite("candidate_quantile", candidate_quantile)
    if not 0 < strong_q < candidate_q < 0.5:
        raise ValueError("INVALID_QUANTILE_THRESHOLDS")
    cap = None if capacity_cap is None else _finite("capacity_cap", capacity_cap)
    if cap is not None and (cap <= 0 or "volume" not in df.columns):
        raise ValueError("CAPACITY_FILTER_REQUIRES_POSITIVE_CAP_AND_VOLUME")
    if "timestamp" in df.columns:
        if not df["timestamp"].is_sorted():
            raise ValueError("TIMESTAMP_MUST_BE_SORTED_ASCENDING")
        if df["timestamp"].n_unique() != df.height:
            raise ValueError("DUPLICATE_TIMESTAMPS_NOT_ALLOWED")

    close = pl.col("close").cast(pl.Float64)
    ma_name = f"ma_{window_size}"
    out = df.with_columns([
        close.rolling_mean(window_size=window_size, min_samples=window_size).alias(ma_name),
    ])
    out = out.with_columns([
        ((close - pl.col(ma_name)) / pl.col(ma_name)).alias("relative_deviation"),
        close.rolling_std(window_size=window_size, min_samples=window_size).alias("_price_std"),
    ])
    out = out.with_columns([
        ((close - pl.col(ma_name)) / pl.col("_price_std")).alias("zscore"),
    ])
    z = pl.col("zscore")
    out = out.with_columns([
        z.rolling_quantile(quantile=strong_q, window_size=quantile_window, min_samples=quantile_min_samples).shift(1).alias("strong_threshold"),
        z.rolling_quantile(quantile=candidate_q, window_size=quantile_window, min_samples=quantile_min_samples).shift(1).alias("candidate_threshold"),
    ])
    if "volume" in out.columns:
        out = out.with_columns((pl.col("volume").cast(pl.Float64) * close).alias("turnover"))
    else:
        out = out.with_columns(pl.lit(None, dtype=pl.Float64).alias("turnover"))
    valid = (
        close.is_finite() & (close > 0) & pl.col("_price_std").is_finite() & (pl.col("_price_std") > 0)
        & z.is_finite() & pl.col("strong_threshold").is_finite() & pl.col("candidate_threshold").is_finite()
    ).fill_null(False)
    if cap is None:
        strong_ok = pl.lit(True)
    else:
        strong_ok = pl.col("turnover").is_finite() & (pl.col("turnover") <= cap)
    out = out.with_columns([
        pl.when(~valid).then(pl.lit("NO_TRADE"))
        .when((z <= pl.col("strong_threshold")) & strong_ok).then(pl.lit("BUY_STRONG"))
        .when(z <= pl.col("candidate_threshold")).then(pl.lit("CANDIDATE"))
        .otherwise(pl.lit("NO_TRADE")).alias("bnf_signal"),
        pl.lit("RESEARCH_ONLY_NOT_EXECUTION").alias("decision_use"),
    ])
    return out.drop("_price_std")


def unified_research_gate(
    *, trade_returns: Sequence[float] | None = None, tested_trial_count: int | None = None,
    cost_metadata: Mapping[str, Any] | None = None,
    fold_returns: Sequence[Sequence[float]] | None = None,
    minimum_sample_size: int = 100, minimum_fold_positive_fraction: float = 0.70,
    bootstrap_repetitions: int = 1999, bootstrap_seed: int = 421,
    alpha: float = 0.05, block_length: int | None = None,
) -> dict[str, Any]:
    """Compute evidence from observed net trade returns; caller-supplied pass flags are forbidden.

    With only one candidate return series, the p-value correction uses the conservative
    trial-count upper bound min(1, p*m). This can establish a sufficient condition for
    BH/FDR passage, but cannot reconstruct exact family-wide BH values without every
    tested trial's p-value. Unknown/missing evidence fails closed.
    """
    if tested_trial_count is None or cost_metadata is None:
        return {"version": QROS_RESEARCH_CONTROLS_VERSION, "status": LEGACY_GATE_STATUS,
                "reason": "TRIAL_COUNT_AND_COST_PROVENANCE_REQUIRED",
                "failed_checks": ["OBSERVED_EVIDENCE_INPUTS_REQUIRED"],
                "execution_authorized": False, "decision_use": "RESEARCH_ONLY"}
    if isinstance(tested_trial_count, bool) or not isinstance(tested_trial_count, int) or tested_trial_count < 1:
        raise ValueError("TESTED_TRIAL_COUNT_MUST_BE_POSITIVE_INTEGER")
    valid_costs, cost_failures = _validate_cost_metadata(cost_metadata, len(trade_returns) if trade_returns is not None else 1)
    if not valid_costs:
        return {"version": QROS_RESEARCH_CONTROLS_VERSION, "status": "NO_TRADE_COST_PROVENANCE_INVALID",
                "reason": "COST_LOG_AND_NET_RETURN_BASIS_NOT_VERIFIED",
                "failed_checks": ["cost_provenance_structurally_valid", "verified_net_returns_required"],
                "cost_metadata_failures": cost_failures, "execution_authorized": False,
                "decision_use": "RESEARCH_ONLY"}
    if trade_returns is None or fold_returns is None:
        return {"version": QROS_RESEARCH_CONTROLS_VERSION, "status": "NO_TRADE_NET_RETURNS_OR_FOLDS_MISSING",
                "reason": "ORDERED_NET_RETURNS_AND_WALK_FORWARD_FOLDS_REQUIRED",
                "failed_checks": ["trade_returns_required", "fold_returns_required"],
                "execution_authorized": False, "decision_use": "RESEARCH_ONLY"}
    if isinstance(minimum_sample_size, bool) or not isinstance(minimum_sample_size, int) or minimum_sample_size < 2:
        raise ValueError("MINIMUM_SAMPLE_SIZE_MUST_BE_AT_LEAST_2")
    alpha_value = _finite("alpha", alpha)
    if not 0 < alpha_value < 1:
        raise ValueError("ALPHA_MUST_BE_IN_(0,1)")
    positive_fraction_limit = _finite("minimum_fold_positive_fraction", minimum_fold_positive_fraction)
    if not 0 < positive_fraction_limit <= 1:
        raise ValueError("INVALID_MINIMUM_FOLD_POSITIVE_FRACTION")

    returns = _validate_return_series(trade_returns, "trade_return", minimum=2)
    if len(returns) < minimum_sample_size:
        stats = {"observation_count": len(returns), "mean_net_return": math.fsum(returns) / len(returns)}
        stats_result = None
    else:
        stats_result = _block_bootstrap_evidence(
            returns, repetitions=bootstrap_repetitions, seed=bootstrap_seed, block_length=block_length
        )
        stats = {"observation_count": len(returns), **stats_result}

    valid_costs, cost_failures = _validate_cost_metadata(cost_metadata, len(returns))
    if isinstance(fold_returns, (str, bytes)) or not isinstance(fold_returns, Sequence) or len(fold_returns) < 3:
        fold_stats = {"fold_count": 0, "positive_fold_fraction": 0.0, "fold_mean_returns": []}
        fold_valid = False
    else:
        folds = [_validate_return_series(fold, f"fold_{i}", minimum=2) for i, fold in enumerate(fold_returns)]
        fold_means = [math.fsum(fold) / len(fold) for fold in folds]
        positive_fraction = sum(value > 0 for value in fold_means) / len(fold_means)
        fold_stats = {"fold_count": len(folds), "positive_fold_fraction": positive_fraction,
                      "fold_mean_returns": fold_means, "minimum_fold_mean": min(fold_means),
                      "maximum_fold_mean": max(fold_means)}
        fold_valid = positive_fraction >= positive_fraction_limit

    enough_data = len(returns) >= minimum_sample_size
    if stats_result is None:
        adjusted_p_upper = 1.0
        ci_lower = None
        ci_upper = None
        p_value = 1.0
        positive_mean = math.fsum(returns) / len(returns) > 0
    else:
        p_value = stats_result["one_sided_p_value"]
        adjusted_p_upper = min(1.0, p_value * tested_trial_count)
        ci_lower, ci_upper = stats_result["ci_95_lower"], stats_result["ci_95_upper"]
        positive_mean = stats_result["mean_net_return"] > 0
    checks = {
        "minimum_sample_size": enough_data,
        "positive_mean_net_return": positive_mean,
        "bootstrap_ci_lower_positive": ci_lower is not None and ci_lower > 0,
        "trial_adjusted_fdr_sufficient_condition": adjusted_p_upper <= alpha_value,
        "cost_provenance_structurally_valid": valid_costs,
        "fold_stability": fold_valid,
    }
    failed = [key for key, passed in checks.items() if not passed]
    return {
        "version": QROS_RESEARCH_CONTROLS_VERSION,
        "status": "CANDIDATE_FOR_FURTHER_REVIEW" if not failed else "NO_TRADE",
        "checks": checks, "failed_checks": failed, "cost_metadata_failures": cost_failures,
        "observation_count": len(returns), "tested_trial_count": tested_trial_count,
        "mean_net_return": stats.get("mean_net_return"),
        "bootstrap_ci_95": None if ci_lower is None else [ci_lower, ci_upper],
        "raw_one_sided_p_value": p_value,
        "conservative_trial_adjusted_p_upper_bound": adjusted_p_upper,
        "multiple_testing_method": "CONSERVATIVE_BH_PASS_BOUND; exact family BH requires all trial p-values",
        "fold_stability": fold_stats, "cost_metadata": dict(cost_metadata),
        "execution_authorized": False, "decision_use": "RESEARCH_ONLY",
    }


def build_audit_record(
    *, input_payload: dict[str, Any], decision: dict[str, Any],
    source_commit: str, config_version: str,
) -> dict[str, Any]:
    """Build deterministic provenance record with canonical SHA-256 hashes."""
    if not source_commit or not config_version:
        raise ValueError("SOURCE_COMMIT_AND_CONFIG_VERSION_REQUIRED")
    canonical_input = json.dumps(input_payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    canonical_decision = json.dumps(decision, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "version": QROS_RESEARCH_CONTROLS_VERSION, "source_commit": source_commit,
        "config_version": config_version,
        "input_sha256": hashlib.sha256(canonical_input.encode("utf-8")).hexdigest(),
        "decision_sha256": hashlib.sha256(canonical_decision.encode("utf-8")).hexdigest(),
        "decision": decision, "execution_authorized": False,
    }


__all__ = [
    "QROS_RESEARCH_CONTROLS_VERSION", "LEGACY_GATE_STATUS",
    "calculate_quarter_kelly_size", "apply_bnf_mean_reversion",
    "unified_research_gate", "build_audit_record",
]
