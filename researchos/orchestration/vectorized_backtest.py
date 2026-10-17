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
    blocked = np.zeros(len(timestamps), dtype=bool)
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
    for i in np.searchsorted(timestamps, news):
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
    passed = np.zeros(len(p), dtype=bool)
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
) -> tuple[float, float, float]:
    values = np.asarray(values, dtype=np.float64)
    signal_indices = np.asarray(signal_indices, dtype=np.int64)
    day_axis = timestamps[hold_start:].astype("datetime64[D]")
    days = np.unique(day_axis)
    if len(days) < max(20, block_days) or not len(values):
        return (float(values.mean()) if len(values) else 0.0, float("-inf"), 1.0)
    sums = np.zeros(len(days))
    counts = np.zeros(len(days))
    ids = np.searchsorted(days, timestamps[signal_indices].astype("datetime64[D]"))
    np.add.at(sums, ids, values)
    np.add.at(counts, ids, 1.0)
    observed = float(values.mean())
    block = min(block_days, len(days))
    blocks = math.ceil(len(days) / block)
    starts = rng.integers(0, len(days), size=(reps, blocks))
    offsets = np.arange(block)
    ix = ((starts[:, :, None] + offsets[None, None, :]) % len(days)).reshape(reps, -1)[
        :, : len(days)
    ]
    sampled_sums = sums[ix].sum(axis=1)
    sampled_counts = counts[ix].sum(axis=1)
    valid = sampled_counts > 0
    means = np.full(reps, np.nan)
    means[valid] = sampled_sums[valid] / sampled_counts[valid]
    centered = sums - observed * counts
    null_sums = centered[ix].sum(axis=1)
    null_means = np.full(reps, np.nan)
    null_means[valid] = null_sums[valid] / sampled_counts[valid]
    return (
        observed,
        float(np.nanquantile(means, 0.025)),
        float(
            (1 + np.count_nonzero(null_means[valid] >= observed)) / (1 + np.count_nonzero(valid))
        ),
    )


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
    gap_prefix = np.cumsum(gap)
    rng = np.random.default_rng(config.random_seed)
    specs = [
        (lb, z, tp, sl, hz, nb)
        for lb in config.lookbacks
        for z in config.z_thresholds
        for tp in config.take_profit_atr
        for sl in config.stop_loss_atr
        for hz in config.horizons
        for nb in config.news_buffers_bars
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
        {nb: load_news_mask(news_csv, data["timestamp"], nb) for nb in config.news_buffers_bars}
        if news_csv
        else {nb: np.zeros(n, dtype=bool) for nb in config.news_buffers_bars}
    )
    results = []
    for start in range(0, len(specs), max(1, config.candidate_chunk_size)):
        for lb, z, tp, sl, hz, nb in specs[start : start + max(1, config.candidate_chunk_size)]:
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
            direction = np.sign(score[sig])
            entry_ix = sig + 1
            entry = o[entry_ix]
            risk = atr[sig]
            tp_price = entry + direction * tp * risk
            sl_price = entry - direction * sl * risk
            exit_price = c[sig + hz].copy()
            alive = np.ones(len(sig), bool)
            for step in range(hz):
                j = entry_ix + step
                long = direction > 0
                stop = alive & np.where(long, low[j] <= sl_price, h[j] >= sl_price)
                take = alive & ~stop & np.where(long, h[j] >= tp_price, low[j] <= tp_price)
                exit_price[stop] = sl_price[stop]
                exit_price[take] = tp_price[take]
                alive[stop | take] = False
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
            mean, lower, pval = (
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
                else (0.0, float("-inf"), 1.0)
            )
            if not costs_verified:
                pval = 1.0
            results.append(
                {
                    "params": params,
                    "trades": int(len(sig)),
                    "holdout_trades": int(oos.sum()),
                    "gross_expectancy": float(gross[oos].mean()) if oos.any() else None,
                    "net_expectancy": float(mean) if costs_verified else None,
                    "ci_lower": float(lower) if costs_verified else None,
                    "gross_ci_lower_diagnostic_only": float(lower) if not costs_verified else None,
                    "p_value": pval,
                    "fdr_pass": False,
                    "status": "COST_MODEL_UNVERIFIED"
                    if not costs_verified
                    else "TESTED_NOT_CERTIFIED",
                }
            )
    pvals = np.array([r["p_value"] for r in results])
    fdr, cutoff = _bh(pvals, config.fdr_q)
    for i, r in enumerate(results):
        r["fdr_pass"] = bool(fdr[i])
        if r["status"] == "COST_MODEL_UNVERIFIED":
            r["status"] = "NO_TRADE_COST_AUDIT_UNVERIFIED"
        else:
            ci_lower = r.get("ci_lower")
            if isinstance(ci_lower, (int, float)) and ci_lower > 0 and fdr[i]:
                r["status"] = "EDGE_CANDIDATE_REQUIRES_INDEPENDENT_CONFIRMATION"
    certified = [
        r
        for r in results
        if r["status"] == "EDGE_CANDIDATE_REQUIRES_INDEPENDENT_CONFIRMATION" and costs_verified
    ]
    return {
        "schema_version": "qros.vectorized-backtest.v1",
        "research_only": True,
        "status": "EDGE_CANDIDATE_REQUIRES_INDEPENDENT_CONFIRMATION"
        if certified
        else ("NO_TRADE_COST_AUDIT_UNVERIFIED" if not costs_verified else "NO_CERTIFIED_EDGE"),
        "rows": n,
        "candidate_count": len(results),
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
            "p_value_cutoff": cutoff,
            "discoveries": int(fdr.sum()),
        },
        "bootstrap": {
            "replicates": config.bootstrap_replicates,
            "block_trading_days": config.bootstrap_block_trading_days,
            "confidence": "95% percentile interval using circular blocks of consecutive observed trading days; no synthetic weekend bars",
        },
        "candidates": results,
        "config": asdict(config),
    }


def write_report(report: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, indent=2, default=str, allow_nan=False) + "\n", encoding="utf-8"
    )
