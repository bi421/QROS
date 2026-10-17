"""Vectorized XAUUSD research backtester with fail-closed cost/edge certification."""

from __future__ import annotations
import json
import math
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import numpy as np
import polars as pl


@dataclass(frozen=True)
class EngineConfig:
    lookbacks: tuple[int, ...] = (4, 8, 16)
    z_thresholds: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0)
    take_profit_atr: tuple[float, ...] = (1.0, 1.5, 2.0)
    stop_loss_atr: tuple[float, ...] = (0.75, 1.0, 1.5)
    horizons: tuple[int, ...] = (8, 16, 32)
    news_buffers_bars: tuple[int, ...] = (0, 1, 2)
    candidate_chunk_size: int = 64
    bootstrap_replicates: int = 1000
    bootstrap_block_trading_days: int = 20
    fdr_q: float = 0.05
    cost_alpha_price: float | None = None
    base_spread_price: float | None = None
    commission_roundtrip_price: float | None = None
    cost_model_verified: bool = False
    random_seed: int = 421


def load_ohlcv_csv(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    with source.open("rb") as probe:
        bom = probe.read(2)
    if bom == b"\xff\xfe":
        normalized = source.with_suffix(".utf8.csv")
        if not normalized.exists() or normalized.stat().st_mtime < source.stat().st_mtime:
            with (
                source.open("r", encoding="utf-16") as src,
                normalized.open("w", encoding="utf-8", newline="") as dst,
            ):
                shutil.copyfileobj(src, dst, 1024 * 1024)
        source = normalized
    frame = pl.read_csv(
        source,
        has_header=False,
        new_columns=["timestamp", "open", "high", "low", "close", "tick_volume", "real_volume"],
        schema_overrides={"timestamp": pl.String},
        infer_schema_length=1000,
        encoding="utf8",
    )
    frame = frame.with_columns(
        pl.col("timestamp")
        .str.strptime(pl.Datetime, format="%Y.%m.%d %H:%M", strict=False)
        .alias("ts")
    )
    if frame["ts"].null_count():
        raise ValueError("Timestamp parse failed; expected YYYY.MM.DD HH:MM")
    frame = frame.sort("ts")
    if frame["ts"].is_duplicated().any():
        raise ValueError("Duplicate timestamps: refusing ambiguous data")
    out = {
        k: frame[k].to_numpy().astype(np.float64, copy=False)
        for k in ("open", "high", "low", "close", "tick_volume", "real_volume")
    }
    for k in ("open", "high", "low", "close"):
        if not np.isfinite(out[k]).all():
            raise ValueError(f"Non-finite {k}")
    if (
        np.any(out["high"] < np.maximum(out["open"], out["close"]))
        or np.any(out["low"] > np.minimum(out["open"], out["close"]))
        or np.any(out["high"] < out["low"])
    ):
        raise ValueError("Invalid OHLC geometry")
    out["timestamp"] = frame["ts"].to_numpy()
    return out


def load_news_mask(path: str | Path | None, timestamps: np.ndarray, buffer_bars: int) -> np.ndarray:
    blocked: np.ndarray = np.zeros(len(timestamps), dtype=bool)
    if path is None:
        return blocked
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"News file does not exist: {p}")
    f = pl.read_csv(p)
    col = next((c for c in ("timestamp", "time", "datetime", "date") if c in f.columns), None)
    if col is None:
        raise ValueError("News CSV needs timestamp/time/datetime/date column")
    news = f[col].cast(pl.String).str.to_datetime(strict=False).drop_nulls().to_numpy()
    if not len(news):
        raise ValueError("No parseable news timestamps")
    news_indices: np.ndarray = np.asarray(np.searchsorted(timestamps, news), dtype=np.int64).reshape(-1)
    for i in news_indices:
        blocked[max(0, int(i) - buffer_bars) : min(len(blocked), int(i) + buffer_bars + 1)] = True
    return blocked


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    prev = np.r_[np.nan, close[:-1]]
    tr = np.maximum(high - low, np.maximum(abs(high - prev), abs(low - prev)))
    tr[0] = high[0] - low[0]
    out = np.full(len(close), np.nan)
    if len(close) >= period:
        out[period - 1 :] = np.convolve(tr, np.ones(period), mode="valid") / period
    return out


def _bh(p: np.ndarray, q: float) -> tuple[np.ndarray, float | None]:
    ids = np.flatnonzero(np.isfinite(p))
    passed: np.ndarray = np.zeros(len(p), dtype=bool)
    if not len(ids):
        return passed, None
    order = ids[np.argsort(p[ids])]
    hits = np.flatnonzero(p[order] <= q * np.arange(1, len(order) + 1) / len(order))
    if not len(hits):
        return passed, None
    cutoff = float(p[order[hits[-1]]])
    passed[ids] = p[ids] <= cutoff
    return passed, cutoff


def _bootstrap_daily_blocks(
    values: np.ndarray,
    signal_indices: np.ndarray,
    timestamps: np.ndarray,
    hold_start: int,
    reps: int,
    block_days: int,
    rng: np.random.Generator,
) -> tuple[float, float, float, float, float]:
    values = np.asarray(values, dtype=np.float64)
    signal_indices = np.asarray(signal_indices, dtype=np.int64)
    day_axis: np.ndarray = timestamps[hold_start:].astype("datetime64[D]")
    days = np.unique(day_axis)
    if len(days) < max(20, block_days) or not len(values):
        observed = float(values.mean()) if len(values) else 0.0
        return (observed, float("-inf"), float("inf"), 1.0, 1.0)
    sums = np.zeros(len(days))
    counts = np.zeros(len(days))
    ids = np.searchsorted(days, timestamps[signal_indices].astype("datetime64[D]"))
    np.add.at(sums, ids, values)
    np.add.at(counts, ids, 1.0)
    observed = float(values.mean())
    block = min(block_days, len(days))
    blocks = math.ceil(len(days) / block)
    starts = rng.integers(0, len(days), size=(reps, blocks))
    # Prefix sums avoid materializing the much larger (replicates, days)
    # circular-index tensor. Only (replicates, blocks) block aggregates are
    # gathered; ordinary reductions are used because this is not a GEMM.
    remainder = len(days) - block * (blocks - 1)
    sums_twice = np.concatenate((sums, sums))
    counts_twice = np.concatenate((counts, counts))
    centered = sums - observed * counts
    centered_twice = np.concatenate((centered, centered))
    sums_prefix = np.r_[0.0, np.cumsum(sums_twice)]
    counts_prefix = np.r_[0.0, np.cumsum(counts_twice)]
    centered_prefix = np.r_[0.0, np.cumsum(centered_twice)]

    full_starts = starts[:, :-1]
    full_sum_blocks = sums_prefix[full_starts + block] - sums_prefix[full_starts]
    full_count_blocks = counts_prefix[full_starts + block] - counts_prefix[full_starts]
    full_centered_blocks = centered_prefix[full_starts + block] - centered_prefix[full_starts]
    tail_starts = starts[:, -1]
    tail_sums = sums_prefix[tail_starts + remainder] - sums_prefix[tail_starts]
    tail_counts = counts_prefix[tail_starts + remainder] - counts_prefix[tail_starts]
    tail_centered = centered_prefix[tail_starts + remainder] - centered_prefix[tail_starts]
    sampled_sums = full_sum_blocks.sum(axis=1) + tail_sums
    sampled_counts = full_count_blocks.sum(axis=1) + tail_counts
    null_sums = full_centered_blocks.sum(axis=1) + tail_centered
    valid = sampled_counts > 0
    means = np.full(reps, np.nan)
    means[valid] = sampled_sums[valid] / sampled_counts[valid]
    null_means = np.full(reps, np.nan)
    null_means[valid] = null_sums[valid] / sampled_counts[valid]
    return (
        observed,
        float(np.nanquantile(means, 0.025)),
        float(np.nanquantile(means, 0.975)),
        float((1 + np.count_nonzero(null_means[valid] >= observed)) / (1 + np.count_nonzero(valid))),
        float((1 + np.count_nonzero(null_means[valid] <= observed)) / (1 + np.count_nonzero(valid))),
    )


def _apply_barrier_step(
    open_price: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    direction: np.ndarray,
    stop_price: np.ndarray,
    take_price: np.ndarray,
    alive: np.ndarray,
    exit_price: np.ndarray,
) -> None:
    """Apply one OHLC bar, conservatively filling stop gaps at the bar open."""
    long = direction > 0
    stop = alive & np.where(long, low <= stop_price, high >= stop_price)
    take = alive & ~stop & np.where(long, high >= take_price, low <= take_price)
    # Stops crossed by an opening gap fill at the worse open, not the stale stop
    # level. If both barriers touch intrabar, stop-first remains conservative.
    stop_gap = stop & np.where(long, open_price < stop_price, open_price > stop_price)
    exit_price[stop] = stop_price[stop]
    exit_price[stop_gap] = open_price[stop_gap]
    exit_price[take] = take_price[take]
    alive[stop | take] = False


def run_grid(
    data: dict[str, Any], config: EngineConfig, news_csv: str | None = None
) -> dict[str, Any]:
    o, h, low, c = (data[k] for k in ("open", "high", "low", "close"))
    n = len(c)
    if n < 100:
        raise ValueError("At least 100 bars required")
    atr = _atr(h, low, c)
    costs_configured = all(
        v is not None and np.isfinite(v) and v >= 0
        for v in (
            config.base_spread_price,
            config.cost_alpha_price,
            config.commission_roundtrip_price,
        )
    )
    costs_verified = costs_configured and config.cost_model_verified
    timestamps = data["timestamp"]
    gap = np.r_[False, np.diff(timestamps) != np.timedelta64(15, "m")]
    gap_prefix: np.ndarray = np.cumsum(gap)
    rng = np.random.default_rng(config.random_seed)
    # Without a news feed, the buffer parameter has no effect. Collapse its
    # redundant variants instead of counting identical hypotheses multiple times.
    effective_news_buffers = config.news_buffers_bars if news_csv else (0,)
    specs = [
        (lb, z, tp, sl, hz, nb, mode)
        for mode in ("FOLLOW_SIGNAL", "REVERSE_SIGNAL")
        for lb in config.lookbacks
        for z in config.z_thresholds
        for tp in config.take_profit_atr
        for sl in config.stop_loss_atr
        for hz in config.horizons
        for nb in effective_news_buffers
    ]
    scores = {}
    for lb in config.lookbacks:
        move = np.full(n, np.nan)
        move[lb:] = c[lb:] - c[:-lb]
        scale = np.full(n, np.nan)
        prior_atr = atr[:-1]
        finite = np.isfinite(prior_atr)
        vals = np.nan_to_num(prior_atr, nan=0.0)
        sums = np.convolve(vals, np.ones(lb), mode="valid")
        counts = np.convolve(finite.astype(float), np.ones(lb), mode="valid")
        scale[lb:] = sums / np.where(counts > 0, counts, np.nan)
        idx = np.arange(n)
        crosses_gap = gap_prefix[idx] - gap_prefix[np.maximum(0, idx - lb)] > 0
        score = move / np.where(scale > 0, scale, np.nan)
        score[crosses_gap] = np.nan
        scores[lb] = score
    news_masks = (
        {nb: load_news_mask(news_csv, data["timestamp"], nb) for nb in effective_news_buffers}
        if news_csv
        else {0: np.zeros(n, dtype=bool)}
    )
    results = []
    paired_samples: dict[tuple[Any, ...], dict[str, dict[str, np.ndarray]]] = {}
    for start in range(0, len(specs), max(1, config.candidate_chunk_size)):
        for lb, z, tp, sl, hz, nb, direction_mode in specs[start : start + max(1, config.candidate_chunk_size)]:
            score = scores[lb]
            idx = np.arange(n)
            contiguous = (idx + hz < n) & (
                (gap_prefix[np.minimum(idx + hz, n - 1)] - gap_prefix) == 0
            )
            sig = np.flatnonzero(
                np.isfinite(score)
                & (abs(score) >= z)
                & np.isfinite(atr)
                & ~news_masks[nb]
                & contiguous
            )
            params = {
                "lookback": lb,
                "z": z,
                "tp_atr": tp,
                "sl_atr": sl,
                "horizon": hz,
                "news_buffer_bars": nb,
                "direction_mode": direction_mode,
            }
            if len(sig) < 20:
                results.append(
                    {
                        "params": params,
                        "trades": int(len(sig)),
                        "p_value": 1.0,
                        "fdr_pass": False,
                        "status": "INSUFFICIENT_TRADES",
                    }
                )
                continue
            direction = np.sign(score[sig]) * (1.0 if direction_mode == "FOLLOW_SIGNAL" else -1.0)
            entry_ix: np.ndarray = sig + 1
            entry = o[entry_ix]
            risk = atr[sig]
            tp_price = entry + direction * tp * risk
            sl_price = entry - direction * sl * risk
            exit_price = c[sig + hz].copy()
            alive: np.ndarray = np.ones(len(sig), bool)
            for step in range(hz):
                j: np.ndarray = entry_ix + step
                _apply_barrier_step(
                    o[j], h[j], low[j], direction, sl_price, tp_price, alive, exit_price
                )
            gross = direction * (exit_price - entry)
            net = gross.copy()
            if costs_configured:
                finite_atr = np.isfinite(atr)
                atr_sum = np.r_[0.0, np.cumsum(np.nan_to_num(atr, nan=0.0))]
                atr_count = np.r_[0.0, np.cumsum(finite_atr.astype(float))]
                starts = np.maximum(0, sig - 95)
                base = (atr_sum[sig + 1] - atr_sum[starts]) / np.maximum(
                    1.0, atr_count[sig + 1] - atr_count[starts]
                )
                cost = (
                    config.base_spread_price
                    + config.cost_alpha_price * (risk / base)
                    + config.commission_roundtrip_price
                )
                net = gross - cost
            hold_start = int(n * 0.8)
            oos = sig >= hold_start
            values = net[oos]
            pair_key = (lb, z, tp, sl, hz, nb)
            paired_samples.setdefault(pair_key, {})[direction_mode] = {
                "indices": sig[oos].copy(),
                "gross": gross[oos].copy(),
                "net": net[oos].copy(),
            }
            mean, lower, upper, pval_positive, pval_negative = (
                _bootstrap_daily_blocks(
                    values,
                    sig[oos],
                    timestamps,
                    hold_start,
                    config.bootstrap_replicates,
                    config.bootstrap_block_trading_days,
                    rng,
                )
                if len(values)
                else (0.0, float("-inf"), float("inf"), 1.0, 1.0)
            )
            if not costs_verified:
                pval_positive = pval_negative = 1.0
            results.append(
                {
                    "params": params,
                    "trades": int(len(sig)),
                    "holdout_trades": int(oos.sum()),
                    "gross_expectancy": float(gross[oos].mean()) if oos.any() else None,
                    "net_expectancy": float(mean) if costs_verified else None,
                    "ci_lower": float(lower) if costs_verified else None,
                    "gross_ci_lower_diagnostic_only": float(lower) if not costs_verified else None,
                    "ci_upper": float(upper) if costs_verified else None,
                    "gross_ci_upper_diagnostic_only": float(upper) if not costs_verified else None,
                    "p_value": pval_positive,
                    "p_value_positive": pval_positive,
                    "p_value_negative": pval_negative,
                    "fdr_pass": False,
                    "fdr_negative_pass": False,
                    "status": "COST_MODEL_UNVERIFIED"
                    if not costs_verified
                    else "TESTED_NOT_CERTIFIED",
                }
            )
    pvals_positive = np.array([r.get("p_value_positive", 1.0) for r in results])
    pvals_negative = np.array([r.get("p_value_negative", 1.0) for r in results])
    fdr_positive, cutoff_positive = _bh(pvals_positive, config.fdr_q)
    fdr_negative, cutoff_negative = _bh(pvals_negative, config.fdr_q)
    for i, r in enumerate(results):
        r["fdr_pass"] = bool(fdr_positive[i])
        r["fdr_negative_pass"] = bool(fdr_negative[i])
        if r["status"] == "COST_MODEL_UNVERIFIED":
            r["status"] = "NO_TRADE_COST_AUDIT_UNVERIFIED"
        else:
            ci_lower = r.get("ci_lower")
            ci_upper = r.get("ci_upper")
            if isinstance(ci_lower, (int, float)) and ci_lower > 0 and fdr_positive[i]:
                r["status"] = "EDGE_CANDIDATE_REQUIRES_INDEPENDENT_CONFIRMATION"
            elif isinstance(ci_upper, (int, float)) and ci_upper < 0 and fdr_negative[i]:
                r["status"] = "REJECTED_NEGATIVE_EDGE"
            elif isinstance(ci_lower, (int, float)) and isinstance(ci_upper, (int, float)) and ci_lower <= 0 <= ci_upper:
                r["status"] = "INCONCLUSIVE"
    paired_comparisons: list[dict[str, Any]] = []
    for pair_key, modes in paired_samples.items():
        if "FOLLOW_SIGNAL" not in modes or "REVERSE_SIGNAL" not in modes:
            continue
        follow = modes["FOLLOW_SIGNAL"]
        reverse = modes["REVERSE_SIGNAL"]
        if not np.array_equal(follow["indices"], reverse["indices"]):
            paired_comparisons.append({
                "params": dict(zip(
                    ("lookback", "z", "tp_atr", "sl_atr", "horizon", "news_buffer_bars"),
                    pair_key,
                )),
                "status": "REJECTED_VALIDATION",
                "reason": "directional event indices differ; paired comparison is invalid",
            })
            continue
        gross_diff = follow["gross"] - reverse["gross"]
        net_diff = follow["net"] - reverse["net"]
        diff = net_diff if costs_verified else gross_diff
        hold_indices = follow["indices"]
        hold_start = int(n * 0.8)
        mean_diff, lower_diff, upper_diff, p_diff_positive, p_diff_negative = (
            _bootstrap_daily_blocks(
                diff, hold_indices, timestamps, hold_start,
                config.bootstrap_replicates, config.bootstrap_block_trading_days, rng,
            )
            if len(diff)
            else (0.0, float("-inf"), float("inf"), 1.0, 1.0)
        )
        paired_comparisons.append({
            "params": dict(zip(
                ("lookback", "z", "tp_atr", "sl_atr", "horizon", "news_buffer_bars"),
                pair_key,
            )),
            "holdout_trades": int(len(diff)),
            "gross_expectancy_difference_follow_minus_reverse": float(gross_diff.mean()) if len(gross_diff) else None,
            "net_expectancy_difference_follow_minus_reverse": float(mean_diff) if costs_verified else None,
            "ci_lower": float(lower_diff) if costs_verified else None,
            "ci_upper": float(upper_diff) if costs_verified else None,
            "gross_ci_lower_diagnostic_only": float(lower_diff) if not costs_verified else None,
            "gross_ci_upper_diagnostic_only": float(upper_diff) if not costs_verified else None,
            "p_value_follow_better": p_diff_positive if costs_verified else 1.0,
            "p_value_reverse_better": p_diff_negative if costs_verified else 1.0,
            "fdr_follow_better": False,
            "fdr_reverse_better": False,
            "status": "UNVERIFIED_COSTS" if not costs_verified else "INCONCLUSIVE",
        })
    pair_p_follow = np.array([item["p_value_follow_better"] for item in paired_comparisons])
    pair_p_reverse = np.array([item["p_value_reverse_better"] for item in paired_comparisons])
    pair_fdr_follow, pair_cutoff_follow = _bh(pair_p_follow, config.fdr_q)
    pair_fdr_reverse, pair_cutoff_reverse = _bh(pair_p_reverse, config.fdr_q)
    for i, item in enumerate(paired_comparisons):
        item["fdr_follow_better"] = bool(pair_fdr_follow[i])
        item["fdr_reverse_better"] = bool(pair_fdr_reverse[i])
        if item["status"] == "REJECTED_VALIDATION" or item["status"] == "UNVERIFIED_COSTS":
            continue
        lower_diff = item["ci_lower"]
        upper_diff = item["ci_upper"]
        if isinstance(lower_diff, (int, float)) and lower_diff > 0 and pair_fdr_follow[i]:
            item["status"] = "FOLLOW_SIGNAL_BETTER_REQUIRES_INDEPENDENT_CONFIRMATION"
        elif isinstance(upper_diff, (int, float)) and upper_diff < 0 and pair_fdr_reverse[i]:
            item["status"] = "REVERSE_SIGNAL_BETTER_REQUIRES_INDEPENDENT_CONFIRMATION"
        elif isinstance(lower_diff, (int, float)) and isinstance(upper_diff, (int, float)) and lower_diff <= 0 <= upper_diff:
            item["status"] = "INCONCLUSIVE"
    certified = [
        r
        for r in results
        if r["status"] == "EDGE_CANDIDATE_REQUIRES_INDEPENDENT_CONFIRMATION" and costs_verified
    ]
    return {
        "schema_version": "qros.vectorized-backtest.v2",
        "research_only": True,
        "status": "EDGE_CANDIDATE_REQUIRES_INDEPENDENT_CONFIRMATION"
        if certified
        else ("NO_TRADE_COST_AUDIT_UNVERIFIED" if not costs_verified else "NO_CERTIFIED_EDGE"),
        "rows": n,
        "candidate_count": len(results),
        "grid": {
            "direction_modes": ["FOLLOW_SIGNAL", "REVERSE_SIGNAL"],
            "parameter_combinations": len(results) // 2,
            "news_buffers_evaluated": list(effective_news_buffers),
            "news_buffer_variants_collapsed": not bool(news_csv),
            "reason": "No news CSV supplied; buffer lengths are observationally identical" if not news_csv else None,
        },
        "cost_model": {
            "configured": costs_configured,
            "verified": costs_verified,
            "base_spread_price": config.base_spread_price,
            "alpha_price": config.cost_alpha_price,
            "commission_roundtrip_price": config.commission_roundtrip_price,
            "units": "XAUUSD price units per ounce; broker contract conversion required",
        },
        "holdout": "chronological final 20%; independent untouched holdout required before production certification",
        "fdr": {
            "method": "Benjamini-Hochberg",
            "q": config.fdr_q,
            "p_value_cutoff": cutoff_positive,
            "discoveries": int(fdr_positive.sum()),
            "positive_p_value_cutoff": cutoff_positive,
            "negative_p_value_cutoff": cutoff_negative,
            "positive_discoveries": int(fdr_positive.sum()),
            "negative_discoveries": int(fdr_negative.sum()),
        },
        "bootstrap": {
            "replicates": config.bootstrap_replicates,
            "block_trading_days": config.bootstrap_block_trading_days,
            "confidence": "95% percentile interval using circular blocks of consecutive observed trading days; no synthetic weekend bars",
        },
        "candidates": results,
        "paired_directional_comparisons": paired_comparisons,
        "paired_comparison_fdr": {
            "method": "Benjamini-Hochberg applied separately to paired FOLLOW-minus-REVERSE and REVERSE-minus-FOLLOW hypotheses",
            "q": config.fdr_q,
            "follow_better_p_value_cutoff": pair_cutoff_follow,
            "reverse_better_p_value_cutoff": pair_cutoff_reverse,
            "follow_better_discoveries": int(pair_fdr_follow.sum()),
            "reverse_better_discoveries": int(pair_fdr_reverse.sum()),
        },
        "config": asdict(config),
    }


def write_report(report: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, indent=2, default=str, allow_nan=False) + "\n", encoding="utf-8"
    )
