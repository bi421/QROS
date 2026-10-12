"""Chronological, cash-only Biberion-inspired research sandbox.

Input CSV columns: timestamp,symbol,open,high,low,close,volume,benchmark_close.
Optional: flow_imbalance (positive means favorable buy-side proxy).
Signals are formed at a completed bar and may only fill at the next bar's open.
This is a research simulator, not a broker adapter or profitability claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class Position:
    symbol: str
    entry_time: str
    entry: float
    stop: float
    quantity: float
    notional: float
    initial_risk: float
    additions: int = 0


def _validate(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "symbol", "open", "high", "low", "close", "volume", "benchmark_close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame["symbol"] = frame["symbol"].astype(str)
    if (frame["symbol"].str.strip() == "").any() or (frame["symbol"].str.lower() == "nan").any():
        raise ValueError("symbol must be a non-empty identifier")
    for column in ("open", "high", "low", "close", "volume", "benchmark_close"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if not np.isfinite(frame[column].to_numpy(dtype=float)).all():
            raise ValueError(f"non-finite values in {column}")
    if (frame[["open", "high", "low", "close", "benchmark_close"]] <= 0).any().any():
        raise ValueError("prices must be positive")
    if (frame["volume"] < 0).any():
        raise ValueError("volume must be nonnegative")
    if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("invalid high")
    if (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("invalid low")
    if frame.duplicated(["timestamp", "symbol"]).any():
        raise ValueError("duplicate timestamp/symbol rows")
    frame = frame.sort_values(["timestamp", "symbol"], kind="mergesort").reset_index(drop=True)
    if "flow_imbalance" in frame:
        frame["flow_imbalance"] = pd.to_numeric(frame["flow_imbalance"], errors="coerce")
    else:
        frame["flow_imbalance"] = np.nan
    return frame


def run_backtest(
    data: pd.DataFrame,
    *,
    initial_cash: float = 100_000.0,
    fast: int = 5,
    slow: int = 25,
    volume_window: int = 50,
    volume_k: float = 2.0,
    max_assets: int = 10,
    basket_fraction: float = 0.10,
    asset_fraction: float = 0.01,
    asset_risk_fraction: float = 0.001,
    basket_risk_fraction: float = 0.005,
    stop_buffer_bps: float = 2.0,
    fee_bps: float = 1.0,
    latency_slippage_bps: float = 2.0,
    directionality_min: float = 0.65,
    max_additions: int = 2,
) -> dict:
    """Replay bars without future information; all fractions are equity fractions."""
    if not np.isfinite(initial_cash) or initial_cash <= 0:
        raise ValueError("initial_cash must be finite and positive")
    if fast < 1 or slow <= fast or volume_window < 2 or max_assets < 1:
        raise ValueError("invalid windows or max_assets")
    fractions = (basket_fraction, asset_fraction, asset_risk_fraction, basket_risk_fraction)
    if any(not np.isfinite(x) or x <= 0 for x in fractions):
        raise ValueError("risk fractions must be finite and positive")
    if basket_fraction > 1 or asset_fraction > basket_fraction:
        raise ValueError("invalid allocation caps")
    if stop_buffer_bps < 0 or fee_bps < 0 or latency_slippage_bps < 0:
        raise ValueError("cost and stop buffer parameters must be nonnegative")

    frame = _validate(data)
    dataset_hash = hashlib.sha256(
        frame.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%S.%fZ").encode()
    ).hexdigest()
    timestamps = list(frame["timestamp"].drop_duplicates())
    grouped = {t: part.set_index("symbol") for t, part in frame.groupby("timestamp", sort=True)}
    symbols = sorted(frame["symbol"].astype(str).unique())
    histories: dict[str, list[dict]] = {s: [] for s in symbols}
    positions: dict[str, Position] = {}
    pending: dict[str, dict] = {}
    cash = float(initial_cash)
    trades: list[dict] = []
    equity_points: list[dict] = []
    lockdown_bars = 0
    lockdown = True
    slippage = latency_slippage_bps / 10_000.0
    fee = fee_bps / 10_000.0
    buffer = stop_buffer_bps / 10_000.0

    def mark_equity(bars, price_column: str = "close") -> float:
        value = cash
        for sym, pos in positions.items():
            if sym in bars.index:
                value += pos.quantity * float(bars.loc[sym, price_column])
            else:
                value += pos.notional
        return value

    def close_position(sym: str, px: float, ts, reason: str) -> None:
        nonlocal cash
        pos = positions.pop(sym)
        exit_px = max(np.finfo(float).eps, px * (1.0 - slippage))
        proceeds = pos.quantity * exit_px
        exit_fee = proceeds * fee
        cash += proceeds - exit_fee
        pnl = proceeds - exit_fee - pos.notional - pos.notional * fee
        trades.append({
            "symbol": sym, "entry_time": pos.entry_time, "exit_time": str(ts),
            "entry": pos.entry, "exit": exit_px, "quantity": pos.quantity,
            "pnl_net": pnl, "initial_risk": pos.initial_risk,
            "r_multiple": pnl / pos.initial_risk if pos.initial_risk > 0 else None,
            "additions": pos.additions, "exit_reason": reason,
        })

    for index, ts in enumerate(timestamps):
        bars = grouped[ts]
        # A proposal must execute on the immediately following timestamp; otherwise expire it.
        for pending_symbol in list(pending):
            if pending_symbol not in bars.index:
                pending.pop(pending_symbol, None)
        # Existing stops are evaluated before any current-bar signal; gaps are pessimistic.
        for sym in list(positions):
            if sym not in bars.index:
                continue
            bar = bars.loc[sym]
            pos = positions[sym]
            if float(bar["open"]) <= pos.stop:
                close_position(sym, float(bar["open"]), ts, "gap_stop")
            elif float(bar["low"]) <= pos.stop:
                close_position(sym, pos.stop, ts, "stop")

        # Pending signals from the prior completed bar execute at current open only.
        for sym, proposal in list(pending.items()):
            if sym not in bars.index:
                continue
            bar = bars.loc[sym]
            open_px = float(bar["open"]) * (1.0 + slippage)
            if proposal["kind"] == "exit":
                if sym in positions:
                    close_position(sym, float(bar["open"]), ts, "sideline_lockdown")
            elif proposal["kind"] == "entry":
                if lockdown or sym in positions or len(positions) >= max_assets:
                    pending.pop(sym, None)
                    continue
                equity = mark_equity(bars, "open")
                basket_notional = sum(p.notional for p in positions.values())
                basket_risk = sum(p.initial_risk for p in positions.values())
                stop = float(proposal["stop"])
                if open_px <= stop:
                    pending.pop(sym, None)
                    continue
                stop_gap = open_px - stop
                if stop_gap <= 0:
                    pending.pop(sym, None)
                    continue
                by_asset = equity * asset_fraction
                by_risk = equity * asset_risk_fraction * open_px / stop_gap
                by_basket = max(0.0, equity * basket_fraction - basket_notional)
                by_cash = max(0.0, cash / (1.0 + fee))
                by_total_risk = max(0.0, equity * basket_risk_fraction - basket_risk) * open_px / stop_gap
                notional = min(by_asset, by_risk, by_basket, by_cash, by_total_risk)
                if notional <= 0:
                    pending.pop(sym, None)
                    continue
                qty = notional / open_px
                entry_fee = notional * fee
                cash -= notional + entry_fee
                risk = qty * stop_gap
                positions[sym] = Position(sym, str(proposal["signal_time"]), open_px, stop,
                                          qty, notional, risk)
            else:
                pos = positions.get(sym)
                if pos is not None:
                    equity = mark_equity(bars, "open")
                    new_stop = max(pos.stop, float(proposal["trail_stop"]))
                    cap = max(0.0, equity * asset_fraction - pos.notional)
                    risk_cap = max(0.0, equity * asset_risk_fraction - pos.initial_risk)
                    stop_gap = max(open_px - new_stop, open_px * 1e-6)
                    add_notional = min(cap, risk_cap * open_px / stop_gap,
                                       max(0.0, cash / (1.0 + fee)))
                    if add_notional > 0 and open_px > pos.entry:
                        qty = add_notional / open_px
                        cash -= add_notional * (1.0 + fee)
                        pos.quantity += qty
                        pos.notional += add_notional
                        pos.initial_risk += qty * max(0.0, open_px - new_stop)
                        pos.additions += 1
                        # Use only the previous completed bar to ratchet the stop.
                        pos.stop = new_stop
            pending.pop(sym, None)

        # Benchmark direction consistency uses only benchmark values observed by this timestamp.
        benchmark_history = [float(grouped[prior]["benchmark_close"].iloc[0])
                             for prior in timestamps[: index + 1]]
        changes = np.diff(np.asarray(benchmark_history[-11:], dtype=float))
        nonzero = changes[changes != 0]
        consistency = (max(np.mean(nonzero > 0), np.mean(nonzero < 0))
                       if len(nonzero) else 0.0)
        lockdown = len(changes) < 5 or consistency < directionality_min
        if lockdown:
            lockdown_bars += 1
            # Liquidate active long exposure at the next observable open; no new entries.
            for held_symbol in positions:
                pending[held_symbol] = {"kind": "exit", "signal_time": ts}

        # Winner pyramiding only: explicit flow proxy required, next bar executes the add.
        for sym, pos in list(positions.items()):
            if sym not in bars.index or pos.additions >= max_additions:
                continue
            bar = bars.loc[sym]
            flow = float(bar["flow_imbalance"]) if pd.notna(bar["flow_imbalance"]) else 0.0
            if float(bar["close"]) > pos.entry and flow > 0.0 and not lockdown:
                pending.setdefault(sym, {"kind": "add", "signal_time": ts, "stop": pos.stop,
                                         "trail_stop": float(bar["low"]) * (1.0 - buffer)})

        # Record histories and form signals at this completed bar for next bar only.
        for sym, bar in bars.iterrows():
            histories[sym].append({
                "close": float(bar["close"]), "volume": float(bar["volume"]),
                "low": float(bar["low"]), "flow": bar["flow_imbalance"],
            })
            hist = histories[sym]
            if lockdown or sym in positions or len(hist) < max(slow + 1, volume_window + 1):
                continue
            prior_volumes = np.asarray([x["volume"] for x in hist[-volume_window - 1:-1]])
            threshold = float(prior_volumes.mean() + volume_k * prior_volumes.std(ddof=0))
            surge = float(bar["volume"]) > threshold
            closes = np.asarray([x["close"] for x in hist])
            fast_prev, slow_prev = closes[-fast-1:-1].mean(), closes[-slow-1:-1].mean()
            fast_now, slow_now = closes[-fast:].mean(), closes[-slow:].mean()
            benchmark_up = len(benchmark_history) >= 2 and benchmark_history[-1] > benchmark_history[-2]
            crossed_up = fast_prev <= slow_prev and fast_now > slow_now
            if crossed_up and benchmark_up and surge:
                stop = float(bar["low"]) * (1.0 - buffer)
                if stop > 0 and stop < float(bar["close"]):
                    pending[sym] = {"kind": "entry", "signal_time": ts, "stop": stop}

        equity_points.append({"timestamp": str(ts), "equity": mark_equity(bars),
                              "cash": cash, "positions": len(positions),
                              "sideline_lockdown": bool(lockdown)})

    # Liquidate at final observed close with the same conservative exit penalty.
    final_ts = timestamps[-1] if timestamps else None
    if final_ts is not None:
        final_bars = grouped[final_ts]
        for sym in list(positions):
            final_price = (float(final_bars.loc[sym, "close"]) if sym in final_bars.index
                           else float(histories[sym][-1]["close"]))
            close_position(sym, final_price, final_ts, "end_of_data")
    final_equity = cash
    pnls = np.asarray([t["pnl_net"] for t in trades], dtype=float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    equity_series = np.asarray([p["equity"] for p in equity_points] + [final_equity], dtype=float)
    peaks = np.maximum.accumulate(equity_series) if len(equity_series) else np.array([initial_cash])
    drawdowns = (equity_series - peaks) / peaks
    result = {
        "schema": "qros.biberion-research.v1",
        "status": "RESEARCH_ONLY_NOT_OOS_VALIDATED",
        "dataset_sha256": dataset_hash,
        "parameters": {
            "fast": fast, "slow": slow, "volume_window": volume_window, "volume_k": volume_k,
            "max_assets": max_assets, "basket_fraction": basket_fraction,
            "asset_fraction": asset_fraction, "asset_risk_fraction": asset_risk_fraction,
            "basket_risk_fraction": basket_risk_fraction, "fee_bps": fee_bps,
            "latency_slippage_bps": latency_slippage_bps,
            "directionality_min": directionality_min, "max_additions": max_additions,
        },
        "summary": {
            "initial_cash": initial_cash, "final_equity": final_equity,
            "net_return_pct": (final_equity / initial_cash - 1.0) * 100.0,
            "max_drawdown_pct": float(-drawdowns.min() * 100.0) if len(drawdowns) else 0.0,
            "trades": len(trades), "win_rate_pct": float((pnls > 0).mean() * 100.0) if len(pnls) else 0.0,
            "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() else None,
            "mean_trade_pnl": float(pnls.mean()) if len(pnls) else 0.0,
            "lockdown_bars": lockdown_bars,
            "fees_and_slippage_modeled": True,
            "live_edge_proven": False,
        },
        "trades": trades,
        "equity_curve": equity_points,
    }
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), default=str).encode()
    result["result_sha256"] = hashlib.sha256(canonical).hexdigest()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--output", type=Path, default=Path("biberion_backtest_result.json"))
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    args = parser.parse_args()
    result = run_backtest(pd.read_csv(args.csv), initial_cash=args.initial_cash)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": result["summary"],
                      "dataset_sha256": result["dataset_sha256"],
                      "result_sha256": result["result_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
