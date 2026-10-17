"""Re-evaluate historical 19 FOLLOW-minus-REVERSE pairs with spread-bar costs.

Historical pairs are recovered by rerunning the original vectorized engine.
Costs are sensitivity assumptions, not verified broker execution costs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import shutil

from researchos.orchestration.vectorized_backtest import (
    _apply_barrier_step,
    _atr,
    _bh,
    _causal_signal_score,
    load_ohlcv_csv,
)
from researchos.orchestration.xauusd_cost_model import (
    cost_config_completeness,
    load_cost_config,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_M15 = Path(r"C:\Users\User\Documents\XAUUSDM15.csv")
SOURCE_M1 = ROOT / "data" / "mt5" / "xauusd" / "XAUUSD_M1_2021_2025_MT5.csv"
ORIGINAL_RERUN = ROOT / "artifacts" / "qros_follow_original_engine_rerun_20261017.json"
COSTS_PATH = ROOT / "config" / "costs.yaml"
OUTPUT_PARQUET = ROOT / "artifacts" / "qros_follow_19_costed_trade_rows_20261017.parquet"
OUTPUT_JSON = ROOT / "artifacts" / "qros_follow_19_cost_reassessment_20261017.json"
BENCHMARK_JSON = ROOT / "artifacts" / "vectorized_xauusd_backtest_fullgrid_benchmark_20261017.json"
OUTPUT_REGISTRY = ROOT / "artifacts" / "qros_historical_trial_registry_20261017.json"
OUTPUT_HASH = ROOT / "artifacts" / "qros_follow_19_costed_trade_rows_20261017.sha256"
MULTIPLIERS = (0.5, 1.0, 1.5, 2.0)
BOOTSTRAP_REPS = 1000
MIN_SAMPLE = 100


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bh_adjusted(p_values: np.ndarray) -> np.ndarray:
    """Return Benjamini-Hochberg adjusted p-values in original order."""
    p_values = np.asarray(p_values, dtype=float)
    order = np.argsort(p_values)
    ranked = p_values[order] * len(p_values) / np.arange(1, len(p_values) + 1)
    adjusted_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    adjusted = np.empty_like(adjusted_sorted)
    adjusted[order] = np.clip(adjusted_sorted, 0.0, 1.0)
    return adjusted


def bootstrap_bar_blocks(
    values: np.ndarray,
    signal_indices: np.ndarray,
    n_bars: int,
    hold_start: int,
    block_bars: int,
    reps: int,
    rng: np.random.Generator,
) -> tuple[float, float, float, float, float]:
    """Circular moving-block bootstrap on the bar timeline, preserving overlap/autocorrelation."""
    values = np.asarray(values, dtype=np.float64)
    event_ix = np.asarray(signal_indices, dtype=np.int64) - int(hold_start)
    timeline_n = int(n_bars - hold_start)
    if not len(values) or timeline_n < max(20, block_bars) or block_bars < 1:
        observed = float(values.mean()) if len(values) else 0.0
        return observed, float("-inf"), float("inf"), 1.0, 1.0
    if np.any(event_ix < 0) or np.any(event_ix >= timeline_n):
        raise ValueError("BOOTSTRAP_EVENT_OUTSIDE_HOLDOUT_TIMELINE")
    sums = np.zeros(timeline_n, dtype=np.float64)
    counts = np.zeros(timeline_n, dtype=np.float64)
    np.add.at(sums, event_ix, values)
    np.add.at(counts, event_ix, 1.0)
    observed = float(values.mean())
    block = min(int(block_bars), timeline_n)
    n_blocks = int(np.ceil(timeline_n / block))
    tail_len = timeline_n - block * (n_blocks - 1)
    starts = rng.integers(0, timeline_n, size=(reps, n_blocks))
    sums2 = np.concatenate((sums, sums))
    counts2 = np.concatenate((counts, counts))
    centered2 = np.concatenate((sums - observed * counts, sums - observed * counts))
    ps = np.r_[0.0, np.cumsum(sums2)]
    pc = np.r_[0.0, np.cumsum(counts2)]
    pz = np.r_[0.0, np.cumsum(centered2)]
    fs = starts[:, :-1]
    sum_full = ps[fs + block] - ps[fs]
    count_full = pc[fs + block] - pc[fs]
    null_full = pz[fs + block] - pz[fs]
    ts = starts[:, -1]
    sum_tail = ps[ts + tail_len] - ps[ts]
    count_tail = pc[ts + tail_len] - pc[ts]
    null_tail = pz[ts + tail_len] - pz[ts]
    sampled_sum = sum_full.sum(axis=1) + sum_tail
    sampled_count = count_full.sum(axis=1) + count_tail
    null_sum = null_full.sum(axis=1) + null_tail
    valid = sampled_count > 0
    means = sampled_sum[valid] / sampled_count[valid]
    null_means = null_sum[valid] / sampled_count[valid]
    return (
        observed,
        float(np.quantile(means, 0.025)),
        float(np.quantile(means, 0.975)),
        float((1 + np.count_nonzero(null_means >= observed)) / (1 + len(null_means))),
        float((1 + np.count_nonzero(null_means <= observed)) / (1 + len(null_means))),
    )


def bootstrap_trade_blocks(
    values: np.ndarray, block_length: int, reps: int, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Circular moving-block bootstrap of time-ordered paired trade returns."""
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim == 1:
        matrix = matrix[:, None]
    if matrix.ndim != 2 or not len(matrix) or not np.isfinite(matrix).all():
        raise ValueError("BOOTSTRAP_REQUIRES_NONEMPTY_FINITE_MATRIX")
    n, series_count = matrix.shape
    block = min(max(1, int(block_length)), n)
    n_blocks = int(np.ceil(n / block))
    tail_len = n - block * (n_blocks - 1)
    starts = rng.integers(0, n, size=(reps, n_blocks))
    doubled = np.concatenate((matrix, matrix), axis=0)
    centered = np.concatenate((matrix - matrix.mean(axis=0), matrix - matrix.mean(axis=0)), axis=0)
    prefix = np.vstack((np.zeros((1, series_count)), np.cumsum(doubled, axis=0)))
    centered_prefix = np.vstack((np.zeros((1, series_count)), np.cumsum(centered, axis=0)))
    full_starts = starts[:, :-1]
    full_sums = prefix[full_starts + block] - prefix[full_starts]
    full_null = centered_prefix[full_starts + block] - centered_prefix[full_starts]
    tail_starts = starts[:, -1]
    tail_sums = prefix[tail_starts + tail_len] - prefix[tail_starts]
    tail_null = centered_prefix[tail_starts + tail_len] - centered_prefix[tail_starts]
    means = (full_sums.sum(axis=1) + tail_sums) / n
    null_means = (full_null.sum(axis=1) + tail_null) / n
    observed = matrix.mean(axis=0)
    lower = np.quantile(means, 0.025, axis=0)
    upper = np.quantile(means, 0.975, axis=0)
    p_positive = (1 + np.count_nonzero(null_means >= observed, axis=0)) / (1 + reps)
    p_negative = (1 + np.count_nonzero(null_means <= observed, axis=0)) / (1 + reps)
    return observed, lower, upper, p_positive, p_negative


def overlap_diagnostics(entry_ix: np.ndarray, exit_ix: np.ndarray) -> dict[str, Any]:
    """Count trade overlaps and peak simultaneous bar-level positions."""
    if not len(entry_ix):
        return {"trade_count": 0, "overlapping_trade_count": 0, "overlap_fraction": 0.0, "peak_concurrent_trades": 0}
    order = np.argsort(entry_ix, kind="stable")
    entries = np.asarray(entry_ix, dtype=np.int64)[order]
    exits = np.asarray(exit_ix, dtype=np.int64)[order]
    running_exit = -1
    overlaps = 0
    for entry, exit_ in zip(entries, exits, strict=True):
        if entry <= running_exit:
            overlaps += 1
        running_exit = max(running_exit, int(exit_))
    points = np.concatenate((entries, exits + 1))
    changes = np.concatenate((np.ones(len(entries), dtype=np.int64), -np.ones(len(exits), dtype=np.int64)))
    event_order = np.argsort(points, kind="stable")
    active = np.cumsum(changes[event_order])
    return {
        "trade_count": int(len(entries)),
        "overlapping_trade_count": int(overlaps),
        "overlap_fraction": float(overlaps / len(entries)),
        "peak_concurrent_trades": int(active.max(initial=0)),
    }


def summarize_cost_scenarios(
    gross: np.ndarray, spread: np.ndarray, commission: np.ndarray, slippage: np.ndarray, mask: np.ndarray
) -> dict[str, Any]:
    gross_mean = float(gross[mask].mean()) if mask.any() else None
    spread_mean = float(spread[mask].mean()) if mask.any() else None
    commission_mean = float(commission[mask].mean()) if mask.any() else None
    slippage_mean = float(slippage[mask].mean()) if mask.any() else None
    scenarios = {
        "gross_before_costs": gross_mean,
        "spread_only_net": float((gross[mask] - spread[mask]).mean()) if mask.any() else None,
        "spread_plus_commission_net": float((gross[mask] - spread[mask] - commission[mask]).mean()) if mask.any() else None,
        "spread_commission_slippage_net": float((gross[mask] - spread[mask] - commission[mask] - slippage[mask]).mean()) if mask.any() else None,
        "mean_spread_cost": spread_mean,
        "mean_commission_cost": commission_mean,
        "mean_slippage_cost": slippage_mean,
    }
    for name, total_cost in (
        ("spread_only", spread_mean),
        ("spread_plus_commission", None if spread_mean is None or commission_mean is None else spread_mean + commission_mean),
        ("spread_commission_slippage", None if spread_mean is None or commission_mean is None or slippage_mean is None else spread_mean + commission_mean + slippage_mean),
    ):
        scenarios[f"{name}_break_even_cost_multiplier"] = (
            float(gross_mean / total_cost) if gross_mean is not None and gross_mean > 0 and total_cost is not None and total_cost > 0 else None
        )
    return scenarios


def validate_gross_pair_consistency(candidates: list[dict[str, Any]], pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Check the 324 stored pair gross differences against their two directional candidate means."""
    candidate_map = {
        tuple(item["params"][k] for k in ("lookback", "z", "tp_atr", "sl_atr", "horizon", "news_buffer_bars", "direction_mode")): item
        for item in candidates
    }
    max_error = 0.0
    for pair in pairs:
        p = pair["params"]
        common = tuple(p[k] for k in ("lookback", "z", "tp_atr", "sl_atr", "horizon", "news_buffer_bars"))
        follow = candidate_map.get((*common, "FOLLOW_SIGNAL"))
        reverse = candidate_map.get((*common, "REVERSE_SIGNAL"))
        if follow is None or reverse is None:
            raise ValueError(f"GROSS_PAIR_DIRECTIONAL_CANDIDATE_MISSING:{common}")
        error = abs(
            (float(follow["gross_expectancy"]) - float(reverse["gross_expectancy"]))
            - float(pair["gross_expectancy_difference_follow_minus_reverse"])
        )
        max_error = max(max_error, error)
        if error > 1e-9:
            raise ValueError(f"GROSS_PAIR_ARTIFACT_INCONSISTENT:{common}:{error}")
    return {"status": "PASS", "paired_comparisons": len(pairs), "max_abs_difference_error": max_error, "tolerance": 1e-9}


def verify_original_gross_reproduction(original: dict[str, Any], historical: dict[str, Any]) -> dict[str, Any]:
    """Recompute the original full-sample grid and compare gross expectancy/trade counts."""
    candidates = historical.get("candidates", [])
    pairs = historical.get("paired_directional_comparisons", [])
    if len(candidates) != 648 or len(pairs) != 324:
        raise ValueError(f"ORIGINAL_ARTIFACT_COUNTS_INVALID:candidates={len(candidates)}:pairs={len(pairs)}")
    artifact_pair_consistency = validate_gross_pair_consistency(candidates, pairs)
    candidate_map = {
        tuple(item["params"][k] for k in ("lookback", "z", "tp_atr", "sl_atr", "horizon", "news_buffer_bars", "direction_mode")): item
        for item in candidates
    }
    n = len(original["close"])
    o, h, low, close = (np.asarray(original[k], dtype=np.float64) for k in ("open", "high", "low", "close"))
    timestamps = np.asarray(original["timestamp"]).astype("datetime64[ns]")
    atr = _atr(h, low, close)
    hold_start = int(n * 0.8)
    score_cache = {lb: _causal_signal_score(close, atr, timestamps, lb) for lb in (4, 8, 16)}
    max_mean_error = 0.0
    compared = 0
    for pair in pairs:
        p = pair["params"]
        lb, z, tp, sl, hz = int(p["lookback"]), float(p["z"]), float(p["tp_atr"]), float(p["sl_atr"]), int(p["horizon"])
        score = score_cache[lb]
        idx = np.arange(n)
        gap = np.r_[False, np.diff(timestamps) != np.timedelta64(15, "m")]
        gap_prefix = np.cumsum(gap)
        contiguous = (idx + hz < n) & ((gap_prefix[np.minimum(idx + hz, n - 1)] - gap_prefix) == 0)
        sig = np.flatnonzero(np.isfinite(score) & (np.abs(score) >= z) & np.isfinite(atr) & contiguous)
        if not len(sig):
            raise ValueError(f"ORIGINAL_GROSS_NO_TRADES:{p}")
        directional_means = {}
        for mode, sign in (("FOLLOW_SIGNAL", 1.0), ("REVERSE_SIGNAL", -1.0)):
            direction = np.sign(score[sig]) * sign
            entry_ix = sig + 1
            entry = o[entry_ix]
            risk = atr[sig]
            take = entry + direction * tp * risk
            stop = entry - direction * sl * risk
            exit_price = close[sig + hz].copy()
            alive = np.ones(len(sig), dtype=bool)
            for step in range(hz):
                j = entry_ix + step
                _apply_barrier_step(o[j], h[j], low[j], direction, stop, take, alive, exit_price)
            gross = direction * (exit_price - entry)
            hold_mask = sig >= hold_start
            key = (lb, z, tp, sl, hz, int(p.get("news_buffer_bars", 0)), mode)
            expected = candidate_map.get(key)
            if expected is None:
                raise ValueError(f"ORIGINAL_GROSS_CANDIDATE_MISSING:{key}")
            if int(expected["trades"]) != len(sig) or int(expected["holdout_trades"]) != int(hold_mask.sum()):
                raise ValueError(f"ORIGINAL_GROSS_TRADE_COUNT_MISMATCH:{key}")
            actual_mean = float(gross[hold_mask].mean())
            error = abs(actual_mean - float(expected["gross_expectancy"]))
            max_mean_error = max(max_mean_error, error)
            if error > 1e-9:
                raise ValueError(f"ORIGINAL_GROSS_EXPECTANCY_MISMATCH:{key}:{actual_mean}:{expected['gross_expectancy']}")
            directional_means[mode] = actual_mean
            compared += 1
        diff = directional_means["FOLLOW_SIGNAL"] - directional_means["REVERSE_SIGNAL"]
        if abs(diff - float(pair["gross_expectancy_difference_follow_minus_reverse"])) > 1e-9:
            raise ValueError(f"ORIGINAL_GROSS_PAIR_DIFF_MISMATCH:{p}")
    return {
        "status": "PASS",
        "source_sha256": sha256(SOURCE_M15),
        "source_rows": n,
        "candidate_variants_compared": compared,
        "paired_comparisons_compared": len(pairs),
        "stored_artifact_pair_consistency": artifact_pair_consistency,
        "max_abs_gross_expectancy_error_price_units": max_mean_error,
        "comparison_tolerance": 1e-9,
    }


def load_spread_bars() -> tuple[pl.DataFrame, str, pl.DataFrame]:
    raw = SOURCE_M1.read_bytes()
    m1 = pl.read_csv(SOURCE_M1).with_columns(
        pl.col("time").str.to_datetime(strict=True, time_zone="UTC")
        .dt.replace_time_zone(None).alias("timestamp"),
        *[pl.col(k).cast(pl.Float64) for k in ("open", "high", "low", "close", "spread")],
    ).sort("timestamp")
    if m1["timestamp"].n_unique() != m1.height:
        raise ValueError("M1_DUPLICATE_TIMESTAMPS")
    if m1["spread"].null_count() or (m1["spread"] < 0).any():
        raise ValueError("M1_SPREAD_INVALID")
    bars = m1.group_by_dynamic(
        "timestamp", every="15m", closed="left", label="left"
    ).agg([
        pl.col("open").first().alias("open"),
        pl.col("high").max().alias("high"),
        pl.col("low").min().alias("low"),
        pl.col("close").last().alias("close"),
        pl.col("timestamp").first().alias("entry_m1_ts"),
        pl.col("timestamp").last().alias("bar_exit_m1_ts"),
        pl.col("spread").first().alias("entry_spread"),
        pl.col("spread").last().alias("bar_exit_spread"),
        pl.len().alias("m1_rows"),
    ]).sort("timestamp")
    return bars, hashlib.sha256(raw).hexdigest(), m1


def build_trade_arrays(
    bars: pl.DataFrame, sig: np.ndarray, direction: np.ndarray,
    tp_atr: float, sl_atr: float, horizon: int, atr: np.ndarray,
    open_price: np.ndarray, high: np.ndarray, low: np.ndarray,
    close: np.ndarray, timestamps: np.ndarray,
) -> dict[str, np.ndarray]:
    entry_ix = sig + 1
    entry = open_price[entry_ix]
    risk = atr[sig]
    tp_price = entry + direction * tp_atr * risk
    sl_price = entry - direction * sl_atr * risk
    exit_price = close[sig + horizon].copy()
    exit_ix = sig + horizon
    exit_reason = np.zeros(len(sig), dtype=np.int8)  # 0=timeout, 1=stop, 2=take
    alive = np.ones(len(sig), dtype=bool)
    for step in range(horizon):
        j = entry_ix + step
        alive_before = alive.copy()
        stop_hit = alive_before & np.where(direction > 0, low[j] <= sl_price, high[j] >= sl_price)
        take_hit = alive_before & ~stop_hit & np.where(direction > 0, high[j] >= tp_price, low[j] <= tp_price)
        _apply_barrier_step(
            open_price[j], high[j], low[j], direction,
            sl_price, tp_price, alive, exit_price,
        )
        just_exited = alive_before & ~alive
        exit_ix[just_exited] = j[just_exited]
        exit_reason[stop_hit] = 1
        exit_reason[take_hit] = 2
    return {
        "signal_ix": sig,
        "entry_ix": entry_ix,
        "exit_ix": exit_ix,
        "exit_reason": exit_reason,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "direction": direction.astype(np.int8),
        "entry_price": entry,
        "exit_price": exit_price,
        "entry_bar_ts": timestamps[entry_ix],
        "entry_ts": bars["entry_m1_ts"].to_numpy()[entry_ix].astype("datetime64[ns]"),
        "exit_ts": timestamps[exit_ix],
        "entry_spread": bars["entry_spread"].to_numpy()[entry_ix].astype(float),
        "entry_atr": atr[entry_ix],
        "exit_atr": atr[exit_ix],
        "gross_return": direction * (exit_price / entry - 1.0),
    }


def resolve_exit_m1_quotes(
    trades: dict[str, np.ndarray],
    m1: pl.DataFrame,
    m15_timestamps: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Resolve TP/SL spread to the first touching M1 minute; flag ambiguous partial buckets."""
    minute_ts = m1["timestamp"].to_numpy().astype("datetime64[ns]")
    minute_high = m1["high"].to_numpy().astype(np.float64)
    minute_low = m1["low"].to_numpy().astype(np.float64)
    minute_spread = m1["spread"].to_numpy().astype(np.float64)
    exit_bar_ts = m15_timestamps[trades["exit_ix"]].astype("datetime64[ns]")
    starts = np.searchsorted(minute_ts, exit_bar_ts, side="left")
    ends = np.searchsorted(minute_ts, exit_bar_ts + np.timedelta64(15, "m"), side="left")
    if np.any(ends <= starts):
        raise ValueError("EXIT_M15_BUCKET_HAS_NO_M1_ROWS")
    rows_per_bucket = ends - starts
    offsets = np.arange(15, dtype=np.int64)
    minute_ids = starts[:, None] + offsets[None, :]
    available = minute_ids < ends[:, None]
    safe_ids = np.minimum(minute_ids, len(minute_ts) - 1)
    directions = trades["direction"][:, None]
    stop_price = trades["sl_price"][:, None]
    take_price = trades["tp_price"][:, None]
    stop_hit = available & np.where(directions > 0, minute_low[safe_ids] <= stop_price, minute_high[safe_ids] >= stop_price)
    take_hit = available & np.where(directions > 0, minute_high[safe_ids] >= take_price, minute_low[safe_ids] <= take_price)
    reason = trades["exit_reason"]
    selected_hit = np.where(reason[:, None] == 1, stop_hit, np.where(reason[:, None] == 2, take_hit, False))
    has_hit = selected_hit.any(axis=1)
    ambiguous_bucket = (reason != 0) & (rows_per_bucket != 15)
    impossible = (reason != 0) & ~has_hit & ~ambiguous_bucket
    if np.any(impossible):
        raise ValueError(f"EXIT_TRIGGER_MINUTE_NOT_FOUND:{int(np.count_nonzero(impossible))}")
    first_hit_offset = selected_hit.argmax(axis=1)
    selected_ids = np.where(reason == 0, ends - 1, starts + first_hit_offset)
    exact = ~ambiguous_bucket & ((reason == 0) | has_hit)
    selected_ids = np.clip(selected_ids, 0, len(minute_ts) - 1)
    spreads = minute_spread[selected_ids].copy()
    exit_ts = minute_ts[selected_ids].copy()
    spreads[~exact] = np.nan
    exit_ts[~exact] = np.datetime64("NaT", "ns")
    return spreads, exit_ts, exact


def run() -> dict[str, Any]:
    if not SOURCE_M15.is_file() or not SOURCE_M1.is_file():
        raise FileNotFoundError("Original M15 or spread-bearing M1 source is missing")
    historical = json.loads(ORIGINAL_RERUN.read_text(encoding="utf-8-sig"))
    all_pairs = historical.get("paired_directional_comparisons", [])
    if len(all_pairs) != 324:
        raise ValueError(f"EXPECTED_324_ORIGINAL_PAIRS_GOT_{len(all_pairs)}")
    historical_follow = [
        p for p in all_pairs
        if isinstance(p.get("gross_ci_lower_diagnostic_only"), (int, float))
        and p["gross_ci_lower_diagnostic_only"] > 0
    ]
    if len(historical_follow) != 19:
        raise ValueError(f"EXPECTED_19_HISTORICAL_FOLLOW_PAIRS_GOT_{len(historical_follow)}")
    historical_keys = {
        tuple(p["params"][k] for k in ("lookback", "z", "tp_atr", "sl_atr", "horizon"))
        for p in historical_follow
    }

    bars, m1_sha, m1 = load_spread_bars()
    # The M1-derived bars must exactly reproduce source M15 OHLC before spread
    # observations are joined. This validates time alignment, not broker identity.
    original = load_ohlcv_csv(SOURCE_M15)
    source_m15_sha = sha256(SOURCE_M15)
    historical_report_sha = sha256(ORIGINAL_RERUN)
    cached_gross = None
    if OUTPUT_JSON.is_file():
        try:
            previous = json.loads(OUTPUT_JSON.read_text(encoding="utf-8-sig"))
            prior_verification = previous.get("original_gross_reproduction", {})
            if (
                prior_verification.get("status") == "PASS"
                and prior_verification.get("source_sha256") == source_m15_sha
                and prior_verification.get("source_rows") == len(original["close"])
                and prior_verification.get("candidate_variants_compared") == 648
                and prior_verification.get("paired_comparisons_compared") == 324
                and previous.get("historical_engine_report_sha256") == historical_report_sha
            ):
                cached_gross = {**prior_verification, "verification_reused_from_prior_run": True}
        except (OSError, ValueError, TypeError):
            cached_gross = None
    gross_verification = cached_gross or verify_original_gross_reproduction(original, historical)
    orig_ts = original["timestamp"].astype("datetime64[us]")
    orig_frame = pl.DataFrame({
        "timestamp": orig_ts,
        "src_open": original["open"], "src_high": original["high"],
        "src_low": original["low"], "src_close": original["close"],
    })
    aligned = orig_frame.join(
        bars.select("timestamp", "open", "high", "low", "close", "entry_spread", "bar_exit_spread", "m1_rows"),
        on="timestamp", how="inner",
    ).sort("timestamp")
    if aligned.height != bars.height:
        raise ValueError(f"SPREAD_BAR_ALIGNMENT_ROW_MISMATCH:{aligned.height}!={bars.height}")
    tol = 0.011
    mismatch = aligned.filter(
        ((pl.col("src_open") - pl.col("open")).abs() >= tol)
        | ((pl.col("src_high") - pl.col("high")).abs() >= tol)
        | ((pl.col("src_low") - pl.col("low")).abs() >= tol)
        | ((pl.col("src_close") - pl.col("close")).abs() >= tol)
    )
    if mismatch.height:
        raise ValueError(f"SPREAD_BAR_OHLC_ALIGNMENT_FAILED:{mismatch.height}")
    # Some session-edge buckets can have fewer source minutes; OHLC alignment above
    # is the required check, while observed first/last spreads remain explicitly logged.
    cost_config = load_cost_config(COSTS_PATH)
    completeness = cost_config_completeness(cost_config)
    if not completeness["cost_basis_declared"]:
        raise ValueError(f"COST_BASIS_INCOMPLETE:{completeness['failures']}")

    o = bars["open"].to_numpy().astype(np.float64)
    h = bars["high"].to_numpy().astype(np.float64)
    lo = bars["low"].to_numpy().astype(np.float64)
    c = bars["close"].to_numpy().astype(np.float64)
    ts = bars["timestamp"].to_numpy().astype("datetime64[ns]")
    n = len(c)
    atr = _atr(h, lo, c)
    hold_start = int(n * 0.8)
    rng = np.random.default_rng(20261017)
    all_family: list[dict[str, Any]] = []
    saved_pairs: list[dict[str, Any]] = []
    trade_rows_count = 0
    part_dir = ROOT / "artifacts" / "_qros_follow_trade_parts"
    shutil.rmtree(part_dir, ignore_errors=True)
    part_dir.mkdir(parents=True, exist_ok=True)
    OUTPUT_PARQUET.unlink(missing_ok=True)

    for pair_no, old_pair in enumerate(all_pairs):
        pair_trade_rows: list[dict[str, Any]] = []
        p = old_pair["params"]
        lb, z, tp, sl, hz = int(p["lookback"]), float(p["z"]), float(p["tp_atr"]), float(p["sl_atr"]), int(p["horizon"])
        score = _causal_signal_score(c, atr, ts, lb)
        idx = np.arange(n)
        gap = np.r_[False, np.diff(ts) != np.timedelta64(15, "m")]
        gap_prefix = np.cumsum(gap)
        contiguous = (idx + hz < n) & ((gap_prefix[np.minimum(idx + hz, n - 1)] - gap_prefix) == 0)
        sig = np.flatnonzero(np.isfinite(score) & (np.abs(score) >= z) & np.isfinite(atr) & contiguous)
        if not len(sig):
            continue

        directional: dict[str, dict[str, np.ndarray]] = {}
        for mode, sign in (("FOLLOW_SIGNAL", 1.0), ("REVERSE_SIGNAL", -1.0)):
            direction = np.sign(score[sig]) * sign
            tr = build_trade_arrays(bars, sig, direction, tp, sl, hz, atr, o, h, lo, c, ts)
            tr["exit_spread"], tr["exit_m1_ts"], tr["exit_spread_exact"] = resolve_exit_m1_quotes(tr, m1, ts)
            entry_px = tr["entry_price"]
            entry_spread_price = tr["entry_spread"] * float(cost_config["symbol_point"]["value"])
            exit_spread_price = tr["exit_spread"] * float(cost_config["symbol_point"]["value"])
            gross_vals = tr["direction"] * (tr["exit_price"] / entry_px - 1.0)
            entry_exec_px = np.where(tr["direction"] > 0, entry_px + entry_spread_price, entry_px)
            exit_exec_px = np.where(tr["direction"] > 0, tr["exit_price"], tr["exit_price"] + exit_spread_price)
            exec_vals = np.where(
                tr["direction"] > 0,
                exit_exec_px / entry_exec_px - 1.0,
                1.0 - exit_exec_px / entry_exec_px,
            )
            spread_base = gross_vals - exec_vals
            commission_base = float(cost_config["commission"]["round_turn_usd_per_lot"]["value"]) / (
                float(cost_config["contract_size"]["value"]) * entry_exec_px
            )
            slip_orders = cost_config["slippage"]["order_types"]
            entry_slip = float(slip_orders["market_entry"]["price_units_per_fill"])
            exit_slip = np.select(
                [tr["exit_reason"] == 2, tr["exit_reason"] == 1],
                [
                    float(slip_orders["tp_limit"]["price_units_per_fill"]),
                    float(slip_orders["sl_stop"]["price_units_per_fill"]),
                ],
                default=float(slip_orders["market_exit"]["price_units_per_fill"]),
            )
            slippage_base = (entry_slip + exit_slip) / entry_exec_px
            exact = tr["exit_spread_exact"]
            spread_base[~exact] = np.nan
            commission_base[~exact] = np.nan
            slippage_base[~exact] = np.nan
            net_by_mult: dict[float, np.ndarray] = {}
            component_by_mult: dict[float, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
            save_this_pair = tuple(p[k] for k in ("lookback", "z", "tp_atr", "sl_atr", "horizon")) in historical_keys
            for mult in MULTIPLIERS:
                spread_cost = spread_base * mult
                commission_cost = commission_base * mult
                slippage_cost = slippage_base * mult
                net_vals = gross_vals - spread_cost - commission_cost - slippage_cost
                net_by_mult[mult] = net_vals
                component_by_mult[mult] = (spread_cost, commission_cost, slippage_cost)
            if save_this_pair:
                for j in range(len(sig)):
                    if not bool(exact[j]):
                        continue
                    row = {
                        "pair_id": f"lb{lb}_z{z:g}_tp{tp:g}_sl{sl:g}_h{hz}",
                        "lookback": lb, "z": z, "tp_atr": tp, "sl_atr": sl, "horizon": hz,
                        "direction_mode": mode, "trade_index": int(j),
                        "signal_ts": str(ts[int(tr["signal_ix"][j])]),
                        "entry_ts": str(tr["entry_ts"][j]), "exit_ts": str(tr["exit_ts"][j]),
                        "exit_m1_ts": str(tr["exit_m1_ts"][j]),
                        "entry_price_bid": float(entry_px[j]), "exit_price_bid": float(tr["exit_price"][j]),
                        "entry_price_executable": float(entry_exec_px[j]),
                        "exit_price_executable": float(exit_exec_px[j]),
                        "direction": int(tr["direction"][j]),
                        "exit_reason": {0: "TIMEOUT", 1: "STOP_LOSS", 2: "TAKE_PROFIT"}[int(tr["exit_reason"][j])],
                        "entry_spread_points": float(tr["entry_spread"][j]),
                        "exit_spread_points": float(tr["exit_spread"][j]),
                        "holding_bars": int(tr["exit_ix"][j] - tr["entry_ix"][j] + 1),
                        "entry_atr": float(tr["entry_atr"][j]), "exit_atr": float(tr["exit_atr"][j]),
                        "gross_return": float(gross_vals[j]),
                        "spread_only_net_return": float(gross_vals[j] - spread_base[j]),
                        "spread_plus_commission_net_return": float(gross_vals[j] - spread_base[j] - commission_base[j]),
                        "all_costs_net_return_1x": float(gross_vals[j] - spread_base[j] - commission_base[j] - slippage_base[j]),
                        "holdout_flag": bool(int(tr["signal_ix"][j]) >= hold_start),
                        "costs_verified": bool(completeness["costs_verified"]),
                        "execution_authorized": False,
                    }
                    for mult in MULTIPLIERS:
                        spread_cost, commission_cost, slippage_cost = component_by_mult[mult]
                        row[f"spread_cost_return_x{mult:g}"] = float(spread_cost[j])
                        row[f"commission_cost_return_x{mult:g}"] = float(commission_cost[j])
                        row[f"slippage_cost_return_x{mult:g}"] = float(slippage_cost[j])
                        row[f"total_cost_return_x{mult:g}"] = float(spread_cost[j] + commission_cost[j] + slippage_cost[j])
                        row[f"net_return_x{mult:g}"] = float(net_by_mult[mult][j])
                    pair_trade_rows.append(row)
            directional[mode] = {
                **tr,
                "gross_cost_basis": gross_vals,
                "spread_cost_base": spread_base,
                "commission_cost_base": commission_base,
                "slippage_cost_base": slippage_base,
                **{f"net_{m:g}x": net_by_mult[m] for m in MULTIPLIERS},
            }

        if pair_trade_rows:
            batch = pl.DataFrame(pair_trade_rows)
            batch.write_parquet(part_dir / f"part_{pair_no:03d}.parquet", compression="zstd")
            trade_rows_count += batch.height
            del batch, pair_trade_rows

        follow = directional["FOLLOW_SIGNAL"]
        reverse = directional["REVERSE_SIGNAL"]
        if not np.array_equal(follow["signal_ix"], reverse["signal_ix"]):
            raise ValueError(f"PAIRED_EVENT_MISMATCH:{pair_no}")
        holdout_mask = follow["signal_ix"] >= hold_start
        paired_mask = holdout_mask & follow["exit_spread_exact"] & reverse["exit_spread_exact"]
        f15 = follow["net_1.5x"][paired_mask]
        r15 = reverse["net_1.5x"][paired_mask]
        diff15 = f15 - r15
        holding = follow["exit_ix"] - follow["entry_ix"] + 1
        reverse_holding = reverse["exit_ix"] - reverse["entry_ix"] + 1
        median_follow_holding = float(np.median(holding[paired_mask])) if paired_mask.any() else float(hz)
        median_reverse_holding = float(np.median(reverse_holding[paired_mask])) if paired_mask.any() else float(hz)
        block_length = max(1, int(np.ceil(max(median_follow_holding, median_reverse_holding))))
        if len(diff15) >= 20:
            _, boot_lower, boot_upper, boot_p_pos, boot_p_neg = bootstrap_trade_blocks(
                np.column_stack((f15, r15, diff15)), block_length, BOOTSTRAP_REPS, rng
            )
            lower, upper = float(boot_lower[2]), float(boot_upper[2])
            p_pos, p_neg = float(boot_p_pos[2]), float(boot_p_neg[2])
            p_follow_net_positive, p_reverse_net_positive = float(boot_p_pos[0]), float(boot_p_pos[1])
        else:
            lower, upper, p_pos, p_neg = float("-inf"), float("inf"), 1.0, 1.0
            p_follow_net_positive = p_reverse_net_positive = 1.0
        key = tuple(p[k] for k in ("lookback", "z", "tp_atr", "sl_atr", "horizon"))
        is_historical = key in historical_keys
        follow_scenarios = summarize_cost_scenarios(
            follow["gross_cost_basis"], follow["spread_cost_base"], follow["commission_cost_base"], follow["slippage_cost_base"], paired_mask
        )
        reverse_scenarios = summarize_cost_scenarios(
            reverse["gross_cost_basis"], reverse["spread_cost_base"], reverse["commission_cost_base"], reverse["slippage_cost_base"], paired_mask
        )
        overlap = overlap_diagnostics(follow["entry_ix"][holdout_mask], follow["exit_ix"][holdout_mask])
        row = {
            "params": p, "historical_follow_interval": is_historical,
            "all_trades": int(len(sig)), "holdout_trades": int(holdout_mask.sum()),
            "cost_valid_paired_holdout_trades": int(paired_mask.sum()),
            "ambiguous_exit_spread_excluded_follow": int(np.count_nonzero(holdout_mask & ~follow["exit_spread_exact"])),
            "ambiguous_exit_spread_excluded_reverse": int(np.count_nonzero(holdout_mask & ~reverse["exit_spread_exact"])),
            "ambiguous_exit_spread_excluded_follow_all_period": int(np.count_nonzero(~follow["exit_spread_exact"])),
            "ambiguous_exit_spread_excluded_reverse_all_period": int(np.count_nonzero(~reverse["exit_spread_exact"])),
            "follow_mean_net_by_cost_multiplier": {
                f"{m:g}x": float(np.nanmean(follow[f"net_{m:g}x"])) for m in MULTIPLIERS
            },
            "reverse_mean_net_by_cost_multiplier": {
                f"{m:g}x": float(np.nanmean(reverse[f"net_{m:g}x"])) for m in MULTIPLIERS
            },
            "follow_cost_scenarios_1x": follow_scenarios,
            "reverse_cost_scenarios_1x": reverse_scenarios,
            "holdout_follow_mean_net_1_5x": float(f15.mean()) if len(f15) else None,
            "holdout_reverse_mean_net_1_5x": float(r15.mean()) if len(r15) else None,
            "holdout_follow_minus_reverse_mean_net_1_5x": float(diff15.mean()) if len(diff15) else None,
            "holdout_follow_minus_reverse_ci95_1_5x": [lower, upper],
            "p_value_follow_better_1_5x": float(p_pos),
            "p_value_reverse_better_1_5x": float(p_neg),
            "p_value_follow_net_positive_1_5x": p_follow_net_positive,
            "p_value_reverse_net_positive_1_5x": p_reverse_net_positive,
            "bootstrap": {
                "method": "circular moving-block bootstrap over ordered trades",
                "block_length_trade_observations": block_length,
                "block_length_basis": "ceil(max(median realized FOLLOW/REVERSE holding period in bars))",
                "configured_max_holding_horizon_bars": hz,
                "median_realized_follow_holding_bars": median_follow_holding,
                "median_realized_reverse_holding_bars": median_reverse_holding,
                "holding_period_p95_bars": float(np.quantile(holding[paired_mask], 0.95)) if paired_mask.any() else None,
                "replicates": BOOTSTRAP_REPS,
            },
            "trade_overlap": overlap,
            "follow_cost_screen_1_5x": "INSUFFICIENT_SAMPLE" if len(f15) < MIN_SAMPLE else (
                "REJECTED_COST_FRAGILE" if float(f15.mean()) <= 0 else "SENSITIVITY_ONLY"
            ),
            "reverse_cost_screen_1_5x": "INSUFFICIENT_SAMPLE" if len(r15) < MIN_SAMPLE else (
                "REJECTED_COST_FRAGILE" if float(r15.mean()) <= 0 else "SENSITIVITY_ONLY"
            ),
        }
        all_family.append(row)
        if is_historical:
            saved_pairs.append(row)

    # Correct the paired 1.5x net p-values over the complete 324-pair family.
    p_follow = np.asarray([x["p_value_follow_better_1_5x"] for x in all_family], dtype=float)
    p_reverse = np.asarray([x["p_value_reverse_better_1_5x"] for x in all_family], dtype=float)
    pass_f, cutoff_f = _bh(p_follow, 0.05)
    pass_r, cutoff_r = _bh(p_reverse, 0.05)
    q_follow = bh_adjusted(p_follow)
    q_reverse = bh_adjusted(p_reverse)
    for i, row in enumerate(all_family):
        row["fdr_follow_better_1_5x"] = bool(pass_f[i])
        row["fdr_reverse_better_1_5x"] = bool(pass_r[i])
        row["bh_adjusted_p_follow_better_1_5x"] = float(q_follow[i])
        row["bh_adjusted_p_reverse_better_1_5x"] = float(q_reverse[i])
    for row in saved_pairs:
        match = next(x for x in all_family if x["params"] == row["params"])
        row["fdr_follow_better_1_5x"] = match["fdr_follow_better_1_5x"]
        row["fdr_reverse_better_1_5x"] = match["fdr_reverse_better_1_5x"]

    benchmark = json.loads(BENCHMARK_JSON.read_text(encoding="utf-8-sig"))
    benchmark_candidates = benchmark.get("candidates", [])
    if len(benchmark_candidates) != 972:
        raise ValueError(f"EXPECTED_972_LEGACY_CANDIDATES_GOT_{len(benchmark_candidates)}")
    family_by_params = {
        tuple(x["params"][k] for k in ("lookback", "z", "tp_atr", "sl_atr", "horizon")): x
        for x in all_family
    }
    registry_map: dict[tuple[Any, ...], dict[str, Any]] = {}
    for candidate in benchmark_candidates:
        cp = candidate["params"]
        key = (int(cp["lookback"]), float(cp["z"]), float(cp["tp_atr"]), float(cp["sl_atr"]), int(cp["horizon"]), int(cp["news_buffer_bars"]), "FOLLOW_SIGNAL")
        row = family_by_params.get(key[:5]) if key[5] == 0 else None
        registry_map[key] = {
            "trial_id": "candidate:" + ":".join(str(v) for v in key),
            "family_id": "xauusd_m15_absolute_net_edge_1_5x",
            "params": {**cp, "direction_mode": "FOLLOW_SIGNAL"},
            "sources": ["vectorized_xauusd_backtest_fullgrid_benchmark_20261017.json"],
            "historical_status": "HISTORICAL_COST_UNVERIFIED",
            "p_value_net_positive_1_5x": float(row["p_value_follow_net_positive_1_5x"]) if row else 1.0,
            "p_value_source": "cost_reassessment" if row else "fail_closed_missing_costed_p_value",
        }
    for candidate in historical.get("candidates", []):
        cp = candidate["params"]
        key = (int(cp["lookback"]), float(cp["z"]), float(cp["tp_atr"]), float(cp["sl_atr"]), int(cp["horizon"]), int(cp["news_buffer_bars"]), str(cp["direction_mode"]))
        if key in registry_map:
            registry_map[key]["sources"].append("qros_follow_original_engine_rerun_20261017.json")
            registry_map[key]["historical_status"] = "RECOMPUTED_WITH_COSTS"
        elif str(cp["direction_mode"]) == "REVERSE_SIGNAL":
            # The reverse variants are added from the same 324-pair registry below.
            continue
        else:
            raise ValueError(f"ORIGINAL_CANDIDATE_NOT_IN_HISTORICAL_REGISTRY:{key}")
    for row in all_family:
        cp = row["params"]
        key = (int(cp["lookback"]), float(cp["z"]), float(cp["tp_atr"]), float(cp["sl_atr"]), int(cp["horizon"]), int(cp.get("news_buffer_bars", 0)), "REVERSE_SIGNAL")
        registry_map[key] = {
            "trial_id": "candidate:" + ":".join(str(v) for v in key),
            "family_id": "xauusd_m15_absolute_net_edge_1_5x",
            "params": {**cp, "direction_mode": "REVERSE_SIGNAL"},
            "sources": ["qros_follow_original_engine_rerun_20261017.json", "qros_follow_19_cost_reassessment_20261017.json"],
            "historical_status": "RECOMPUTED_WITH_COSTS",
            "p_value_net_positive_1_5x": float(row["p_value_reverse_net_positive_1_5x"]),
            "p_value_source": "cost_reassessment",
        }
    candidate_trials = list(registry_map.values())
    if len(candidate_trials) != 1296:
        raise ValueError(f"EXPECTED_1296_UNIQUE_CANDIDATE_TRIALS_GOT_{len(candidate_trials)}")
    candidate_q = bh_adjusted(np.asarray([x["p_value_net_positive_1_5x"] for x in candidate_trials], dtype=float))
    candidate_q_map = {}
    for item, q_value in zip(candidate_trials, candidate_q, strict=True):
        item["bh_adjusted_p_value"] = float(q_value)
        item["fdr_pass_q_0_05"] = bool(q_value <= 0.05)
        p = item["params"]
        key5 = tuple(p[k] for k in ("lookback", "z", "tp_atr", "sl_atr", "horizon"))
        candidate_q_map[(key5, p["direction_mode"])] = float(q_value)
    for row in all_family:
        p = row["params"]
        key5 = tuple(p[k] for k in ("lookback", "z", "tp_atr", "sl_atr", "horizon"))
        row["bh_q_follow_net_positive_1_5x_registry"] = candidate_q_map[(key5, "FOLLOW_SIGNAL")]
        row["bh_q_reverse_net_positive_1_5x_registry"] = candidate_q_map[(key5, "REVERSE_SIGNAL")]
        row["fdr_follow_net_edge_1_5x_registry"] = candidate_q_map[(key5, "FOLLOW_SIGNAL")] <= 0.05
        row["fdr_reverse_net_edge_1_5x_registry"] = candidate_q_map[(key5, "REVERSE_SIGNAL")] <= 0.05

    paired_trial_records = []
    for row in all_family:
        paired_trial_records.append({
            "trial_id": "paired:" + ":".join(str(row["params"][k]) for k in ("lookback", "z", "tp_atr", "sl_atr", "horizon")),
            "family_id": "xauusd_m15_follow_vs_reverse_1_5x",
            "params": row["params"],
            "p_follow_better": row["p_value_follow_better_1_5x"],
            "p_reverse_better": row["p_value_reverse_better_1_5x"],
            "bh_q_follow_better": row["bh_adjusted_p_follow_better_1_5x"],
            "bh_q_reverse_better": row["bh_adjusted_p_reverse_better_1_5x"],
        })
    registry = {
        "schema_version": "qros-historical-trial-registry.v1",
        "source_artifacts": {
            "legacy_fullgrid_sha256": sha256(BENCHMARK_JSON),
            "original_engine_rerun_sha256": sha256(ORIGINAL_RERUN),
            "cost_config_sha256": sha256(COSTS_PATH),
        },
        "counts": {
            "legacy_fullgrid_candidate_records": len(benchmark_candidates),
            "original_engine_directional_candidate_records": len(historical.get("candidates", [])),
            "paired_comparison_records": len(all_family),
            "unique_candidate_hypotheses_after_deduplication": len(candidate_trials),
            "total_unique_hypothesis_records_in_registry": len(candidate_trials) + len(paired_trial_records),
        },
        "fdr_families": {
            "absolute_net_edge": {
                "family_id": "xauusd_m15_absolute_net_edge_1_5x",
                "family_size_from_registry": len(candidate_trials),
                "method": "Benjamini-Hochberg",
                "q": 0.05,
                "discoveries": int(np.count_nonzero(candidate_q <= 0.05)),
                "missing_or_historically_unverified_p_values_fail_closed_as_one": True,
            },
            "follow_vs_reverse": {
                "family_id": "xauusd_m15_follow_vs_reverse_1_5x",
                "family_size_from_registry": len(paired_trial_records),
                "method": "Benjamini-Hochberg separately by direction",
                "q": 0.05,
                "follow_discoveries": int(pass_f.sum()),
                "reverse_discoveries": int(pass_r.sum()),
            },
        },
        "candidate_trials": candidate_trials,
        "paired_comparison_trials": paired_trial_records,
        "execution_authorized": False,
    }
    OUTPUT_REGISTRY.write_text(json.dumps(registry, sort_keys=True, indent=2, allow_nan=False, default=str) + "\n", encoding="utf-8")
    registry_sha = sha256(OUTPUT_REGISTRY)

    part_files = list(part_dir.glob("part_*.parquet"))
    if not part_files:
        raise ValueError("NO_HISTORICAL_FOLLOW_TRADE_ROWS_WRITTEN")
    pl.scan_parquet(str(part_dir / "part_*.parquet")).sink_parquet(OUTPUT_PARQUET, compression="zstd")
    shutil.rmtree(part_dir, ignore_errors=True)
    parquet_sha = sha256(OUTPUT_PARQUET)
    cfg_sha = sha256(COSTS_PATH)
    report = {
        "schema_version": "qros-follow-cost-reassessment.v1",
        "decision": "MODELED_COST_SENSITIVITY_ONLY_NOT_BROKER_VERIFIED",
        "historical_engine_report": str(ORIGINAL_RERUN.relative_to(ROOT)),
        "historical_engine_report_sha256": sha256(ORIGINAL_RERUN),
        "historical_pair_count": 19,
        "historical_pair_selection": "The 19 pairs were selected on the original 2017-10-10..2026-10-14 full sample; selection is not independent of the re-evaluation interval.",
        "re_evaluation_source": str(SOURCE_M1.relative_to(ROOT)),
        "original_m15_source": str(SOURCE_M15),
        "m1_dataset_sha256": m1_sha,
        "cost_config": str(COSTS_PATH.relative_to(ROOT)),
        "cost_config_sha256": cfg_sha,
        "cost_basis_declared": completeness["cost_basis_declared"],
        "costs_verified": completeness["costs_verified"],
        "cost_assumptions": completeness["assumption_fields"],
        "quote_basis": "MT5 BID OHLC; long entry ASK / exit BID; short entry BID / exit ASK",
        "commission_assumption_usd_per_lot_round_turn": cost_config["commission"]["round_turn_usd_per_lot"]["value"],
        "slippage_model": cost_config["slippage"]["model"],
        "slippage_assumptions_by_order_type": cost_config["slippage"]["order_types"],
        "entry_timing": "Signal is confirmed at M15 bar close; entry uses the next M15 bar's first observed M1 open and the matching first-row spread.",
        "spread_application": "MT5 BID OHLC; long entry ASK / exit BID, short entry BID / exit ASK. TP/SL spread is from the first M1 minute touching the selected original M15 barrier; timeout spread is from the last M1 row in the exit bar. Incomplete TP/SL M1 buckets are excluded, never filled with a proxy spread.",
        "exit_fill_policy": "Preserves original M15 engine barrier prices and stop-first rule for gross parity. M1 is used to identify the exact observed exit minute and spread; this is not a full M1 quote-side barrier replay.",
        "original_gross_reproduction": gross_verification,
        "m15_alignment": {
            "m1_derived_m15_bars": bars.height,
            "matched_original_m15_rows": aligned.height,
            "ohlc_mismatches": mismatch.height,
            "all_m1_buckets_have_15_rows": bool((bars["m1_rows"] == 15).all()),
            "first_timestamp": str(ts[0]),
            "last_timestamp": str(ts[-1]),
        },
        "holdout": "Final chronological 20% of the overlapping 2021-2025 interval; not an untouched holdout because the 19 pairs were selected on the full original sample.",
        "bootstrap": {
            "method": "circular moving-block bootstrap over ordered trades",
            "replicates": BOOTSTRAP_REPS,
            "block_length": "ceil of the larger median realized holding period (FOLLOW/REVERSE), in ordered trade observations",
            "confidence": "95%",
            "overlap_diagnostics_recorded_per_pair": True,
        },
        "cost_multipliers": list(MULTIPLIERS),
        "cost_scenarios": ["spread_only", "spread_plus_commission", "spread_plus_commission_plus_slippage"],
        "minimum_sample": MIN_SAMPLE,
        "pair_family_size_for_fdr": len(all_family),
        "trial_registry": {
            "path": str(OUTPUT_REGISTRY.relative_to(ROOT)),
            "sha256": registry_sha,
            "unique_candidate_hypotheses": len(candidate_trials),
            "paired_comparison_hypotheses": len(paired_trial_records),
            "total_unique_hypothesis_records": len(candidate_trials) + len(paired_trial_records),
            "absolute_net_edge_fdr_discoveries": int(np.count_nonzero(candidate_q <= 0.05)),
        },
        "fdr": {
            "method": "Benjamini-Hochberg; absolute net-edge family is registry-sized, paired FOLLOW-vs-REVERSE family is separately defined",
            "q": 0.05,
            "candidate_absolute_edge_family_size": len(candidate_trials),
            "candidate_absolute_edge_discoveries": int(np.count_nonzero(candidate_q <= 0.05)),
            "paired_comparison_family_size": len(all_family),
            "follow_p_value_cutoff": cutoff_f, "reverse_p_value_cutoff": cutoff_r,
            "follow_discoveries": int(pass_f.sum()), "reverse_discoveries": int(pass_r.sum()),
        },
        "historical_19_summary": {
            "re_evaluated_pairs": len(saved_pairs),
            "follow_cost_fragile_at_1_5x": sum(x["follow_cost_screen_1_5x"] == "REJECTED_COST_FRAGILE" for x in saved_pairs),
            "follow_insufficient_sample_at_1_5x": sum(x["follow_cost_screen_1_5x"] == "INSUFFICIENT_SAMPLE" for x in saved_pairs),
            "follow_positive_mean_at_1_5x": sum(x["follow_cost_screen_1_5x"] == "SENSITIVITY_ONLY" for x in saved_pairs),
            "ambiguous_exit_spread_excluded_follow_all_period": sum(x["ambiguous_exit_spread_excluded_follow_all_period"] for x in saved_pairs),
            "ambiguous_exit_spread_excluded_reverse_all_period": sum(x["ambiguous_exit_spread_excluded_reverse_all_period"] for x in saved_pairs),
            "fdr_follow_net_edge_discoveries_among_19": sum(x["fdr_follow_net_edge_1_5x_registry"] for x in saved_pairs),
            "fdr_follow_discoveries_among_19": sum(x["fdr_follow_better_1_5x"] for x in saved_pairs),
            "fdr_reverse_discoveries_among_19": sum(x["fdr_reverse_better_1_5x"] for x in saved_pairs),
        },
        "trade_parquet": str(OUTPUT_PARQUET.relative_to(ROOT)),
        "trade_rows": trade_rows_count,
        "trade_parquet_sha256": parquet_sha,
        "historical_19": saved_pairs,
        "full_324_pair_family": all_family,
        "execution_authorized": False,
    }
    OUTPUT_JSON.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False, default=str) + "\n", encoding="utf-8")
    OUTPUT_HASH.write_text(
        f"{parquet_sha}  {OUTPUT_PARQUET.name}\n"
        f"{sha256(OUTPUT_JSON)}  {OUTPUT_JSON.name}\n"
        f"{registry_sha}  {OUTPUT_REGISTRY.name}\n",
        encoding="ascii",
    )
    return {
        "decision": report["decision"], "historical_pairs": len(saved_pairs),
        "family_pairs": len(all_family), "trade_rows": trade_rows_count,
        "parquet": str(OUTPUT_PARQUET), "report": str(OUTPUT_JSON),
        "trial_registry": str(OUTPUT_REGISTRY), "hash_file": str(OUTPUT_HASH),
        "gross_verification": gross_verification,
        "summary": report["historical_19_summary"], "fdr": report["fdr"],
        "alignment": report["m15_alignment"], "costs_verified": report["costs_verified"],
        "execution_authorized": False,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
