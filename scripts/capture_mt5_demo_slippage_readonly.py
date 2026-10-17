"""Read-only capture of recent MT5 demo deals matched to request-time log quotes and historical ticks.

This module NEVER submits, modifies, or closes orders. It aborts unless the connected
MT5 account is explicitly reported by MetaTrader5 as DEMO.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

import MetaTrader5 as mt5
import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PREFIX = "qros_mt5_demo_observed_slippage_20261017"
REQUEST_RE = re.compile(
    r"\t(?P<time>\d{2}:\d{2}:\d{2}\.\d{3})\tTrades\t.*?: market "
    r"(?P<side>buy|sell) (?P<volume>\d+(?:\.\d+)?) (?P<symbol>[A-Z0-9._-]+)(?P<rest>.*)",
    re.IGNORECASE,
)
DONE_RE = re.compile(
    r"\t(?P<time>\d{2}:\d{2}:\d{2}\.\d{3})\tTrades\t.*?: order #(?P<order>\d+) "
    r"(?P<side>buy|sell) (?P<done_volume>\d+(?:\.\d+)?) / "
    r"(?P<requested_volume>\d+(?:\.\d+)?) (?P<symbol>[A-Z0-9._-]+) "
    r"at (?P<price>\d+(?:\.\d+)?) done in (?P<latency>\d+(?:\.\d+)?) ms",
    re.IGNORECASE,
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def parse_log_timestamp(day: datetime, time_text: str) -> datetime:
    hh, mm, rest = time_text.split(":")
    ss, ms = rest.split(".")
    return day.replace(hour=int(hh), minute=int(mm), second=int(ss), microsecond=int(ms) * 1000)


def read_terminal_orders(log_dir: Path, start_utc: datetime, end_utc: datetime) -> tuple[list[dict], dict]:
    requests: list[dict] = []
    completed: list[dict] = []
    source_hashes = {}
    for path in sorted(log_dir.glob("*.log")):
        if not re.fullmatch(r"\d{8}\.log", path.name):
            continue
        day = datetime.strptime(path.stem, "%Y%m%d")
        # Logs use broker/server-local time; collect by file date then resolve UTC offset from MT5 deal history.
        raw = path.read_bytes()
        source_hashes[str(path.name)] = sha256_bytes(raw)
        try:
            if raw[0:2] in (bytes([255, 254]), bytes([254, 255])):
                lines = raw.decode("utf-16", errors="replace").splitlines()
            else:
                lines = raw.decode("utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for line in lines:
            match = REQUEST_RE.search(line)
            if match:
                request_time = parse_log_timestamp(day, match.group("time"))
                requests.append({
                    "log_file": path.name,
                    "log_time": request_time,
                    "side": match.group("side").upper(),
                    "volume": float(match.group("volume")),
                    "symbol": match.group("symbol").upper(),
                    "is_close_request": "close #" in match.group("rest").lower(),
                })
            match = DONE_RE.search(line)
            if match:
                completed.append({
                    "log_file": path.name,
                    "log_time": parse_log_timestamp(day, match.group("time")),
                    "order_id": int(match.group("order")),
                    "side": match.group("side").upper(),
                    "volume": float(match.group("done_volume")),
                    "symbol": match.group("symbol").upper(),
                    "price": float(match.group("price")),
                    "latency_ms": float(match.group("latency")),
                })
    return requests, {"completed_orders": completed, "log_sha256": source_hashes}


def summarize(values: list[float]) -> dict:
    array = np.asarray(values, dtype=np.float64)
    array = array[np.isfinite(array)]
    if not len(array):
        return {"n": 0, "status": "NO_MATCHED_REQUEST_QUOTE_AND_FILL"}
    return {
        "n": int(len(array)),
        "mean_adverse_slippage_price_units": float(array.mean()),
        "median_adverse_slippage_price_units": float(np.median(array)),
        "p90_adverse_slippage_price_units": float(np.quantile(array, 0.90)),
        "p95_adverse_slippage_price_units": float(np.quantile(array, 0.95)),
        "p99_adverse_slippage_price_units": float(np.quantile(array, 0.99)),
        "fraction_adverse": float(np.mean(array > 0)),
        "fraction_price_improved": float(np.mean(array < 0)),
        "status": "PRELIMINARY_MEASURED" if len(array) >= 100 else "INSUFFICIENT_SAMPLE",
    }


def run(days: int = 7) -> dict:
    initialized = mt5.initialize(timeout=10000)
    if not initialized:
        raise RuntimeError(f"MT5_INITIALIZE_FAILED:{mt5.last_error()}")
    try:
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        if terminal is None or not terminal.connected:
            raise RuntimeError("MT5_TERMINAL_NOT_CONNECTED")
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError("ABORTED_NON_DEMO_OR_UNKNOWN_ACCOUNT; no account details were exported")
        now = datetime.now(timezone.utc)
        start_utc = now - timedelta(days=days)
        deals = list(mt5.history_deals_get(start_utc, now) or [])
        deal_by_order: dict[int, list] = {}
        for deal in deals:
            if deal.symbol:
                deal_by_order.setdefault(int(deal.order), []).append(deal)
        log_dir = Path(terminal.data_path) / "logs"
        requests, parsed = read_terminal_orders(log_dir, start_utc, now)
        completed = parsed["completed_orders"]

        offset_seconds = []
        matched_completed = []
        for order in completed:
            matches = [
                deal for deal in deal_by_order.get(order["order_id"], [])
                if deal.symbol.upper() == order["symbol"]
                and abs(float(deal.price) - order["price"]) <= 0.02
                and abs(float(deal.volume) - order["volume"]) <= 1e-8
            ]
            if not matches:
                continue
            for deal in matches:
                deal_utc_naive = datetime.fromtimestamp(deal.time_msc / 1000, timezone.utc).replace(tzinfo=None)
                offset_seconds.append((deal_utc_naive - order["log_time"]).total_seconds())
                matched_completed.append((order, deal))
        if len(offset_seconds) < 3:
            raise RuntimeError(f"INSUFFICIENT_LOG_TO_DEAL_MATCHES_FOR_TIMEZONE:{len(offset_seconds)}")
        offset = round(median(offset_seconds) / 900) * 900
        residuals = [abs(value - offset) for value in offset_seconds]
        if median(residuals) > 5.0:
            raise RuntimeError(f"LOG_DEAL_TIME_OFFSET_NOT_RECONCILED:median_residual_seconds={median(residuals):.3f}")

        # Associate each completion with its preceding market request from the same log file.
        request_for_order = {}
        used_requests = set()
        for order, deal in matched_completed:
            candidates = [
                (i, req) for i, req in enumerate(requests)
                if i not in used_requests
                and req["log_file"] == order["log_file"]
                and req["symbol"] == order["symbol"]
                and req["side"] == order["side"]
                and abs(req["volume"] - order["volume"]) <= 1e-8
                and timedelta(0) <= order["log_time"] - req["log_time"] <= timedelta(seconds=5)
            ]
            if not candidates:
                continue
            i, req = max(candidates, key=lambda pair: pair[1]["log_time"])
            used_requests.add(i)
            request_for_order[order["order_id"]] = req

        observations = []
        request_matched_fill_pairs = 0
        skipped_no_fresh_quote = 0
        max_quote_age_ms = 500
        for order, deal in matched_completed:
            request = request_for_order.get(order["order_id"])
            if request is None:
                continue
            request_matched_fill_pairs += 1
            if deal.symbol.upper() != order["symbol"]:
                continue
            request_utc = (request["log_time"] + timedelta(seconds=offset)).replace(tzinfo=timezone.utc)
            tick_start = request_utc - timedelta(milliseconds=max_quote_age_ms)
            tick_end = request_utc
            ticks = mt5.copy_ticks_range(order["symbol"], tick_start, tick_end, mt5.COPY_TICKS_ALL)
            if ticks is None or len(ticks) == 0:
                skipped_no_fresh_quote += 1
                continue
            req_msc = int(request_utc.timestamp() * 1000)
            eligible = ticks[(ticks["time_msc"] <= req_msc) & ((req_msc - ticks["time_msc"]) <= max_quote_age_ms)]
            if len(eligible) == 0:
                skipped_no_fresh_quote += 1
                continue
            tick = eligible[-1]
            bid, ask = float(tick["bid"]), float(tick["ask"])
            if bid <= 0 or ask <= 0 or ask < bid:
                continue
            side = "BUY" if int(deal.type) == mt5.DEAL_TYPE_BUY else "SELL"
            benchmark = ask if side == "BUY" else bid
            adverse = float(deal.price) - benchmark if side == "BUY" else benchmark - float(deal.price)
            order_type = "market_exit" if request["is_close_request"] else "market_entry"
            ref = sha256_bytes(f"{order['symbol']}|{order['order_id']}|{order['log_file']}".encode())[:16]
            observations.append({
                "symbol": deal.symbol.upper(),
                "order_type": order_type,
                "side": side,
                "request_ts_utc": request_utc.isoformat(timespec="milliseconds"),
                "deal_ts_utc": datetime.fromtimestamp(deal.time_msc / 1000, timezone.utc).isoformat(timespec="milliseconds"),
                "request_quote_bid": bid,
                "request_quote_ask": ask,
                "benchmark_price": benchmark,
                "fill_price": float(deal.price),
                "adverse_slippage_price_units": adverse,
                "volume": float(deal.volume),
                "order_latency_ms": float(order["latency_ms"]),
                "request_quote_age_ms": req_msc - int(tick["time_msc"]),
                "order_ref_hash": ref,
                "source_log_sha256": parsed["log_sha256"][order["log_file"]],
            })

        frame = pl.DataFrame(observations) if observations else pl.DataFrame()
        by_symbol = {}
        if frame.height:
            for symbol in sorted(frame["symbol"].unique().to_list()):
                by_symbol[symbol] = {}
                sym = frame.filter(pl.col("symbol") == symbol)
                for order_type in ("market_entry", "market_exit", "tp_limit", "sl_stop"):
                    values = sym.filter(pl.col("order_type") == order_type)["adverse_slippage_price_units"].to_list()
                    by_symbol[symbol][order_type] = summarize(values)
        else:
            by_symbol = {}
        source_log_sha = parsed["log_sha256"]
        payload = {
            "schema_version": "qros-mt5-demo-slippage-readonly.v1",
            "collection_method": "READ_ONLY_MT5_HISTORY_DEALS_PLUS_REQUEST_LOGS_AND_PRE_REQUEST_TICKS",
            "orders_submitted_by_this_script": 0,
            "account_is_demo": True,
            "window_start_utc": start_utc.isoformat(),
            "window_end_utc": now.isoformat(),
            "deal_history_rows_in_window": len(deals),
            "matched_order_completion_records": len(matched_completed),
            "inferred_log_to_utc_offset_seconds": offset,
            "median_log_deal_time_residual_seconds": float(median(residuals)),
            "observations": len(observations),
            "request_matched_fill_pairs": request_matched_fill_pairs,
            "skipped_no_quote_within_freshness_threshold": skipped_no_fresh_quote,
            "maximum_request_quote_age_ms": max_quote_age_ms,
            "observation_quality": {
                "median_quote_age_ms": float(np.median([row["request_quote_age_ms"] for row in observations])) if observations else None,
                "p95_quote_age_ms": float(np.quantile([row["request_quote_age_ms"] for row in observations], 0.95)) if observations else None,
                "maximum_quote_age_ms": max((row["request_quote_age_ms"] for row in observations), default=None),
                "median_order_latency_ms": float(np.median([row["order_latency_ms"] for row in observations])) if observations else None,
                "p95_order_latency_ms": float(np.quantile([row["order_latency_ms"] for row in observations], 0.95)) if observations else None,
            },
            "by_symbol_and_order_type": by_symbol,
            "tick_benchmark_policy": "For market entries/exits, last available tick at or before the market request log timestamp; BUY benchmark=ask, SELL benchmark=bid. TP/SL are not estimated unless a corresponding request/trigger benchmark can be established.",
            "tp_sl_status": "NO_TRIGGER_BENCHMARK_COLLECTED_BY_THIS_READ_ONLY_PASS",
            "raw_log_hashes": source_log_sha,
            "costs_verified": False,
            "limitations": [
                "This pass only estimates market entry/exit slippage where a request log, order completion, history deal, and pre-request tick can all be reconciled.",
                "TP limit and SL stop slippage are not inferred from market-order records.",
                "Observed sample may be small and account/user behaviour-specific; do not generalize it to all market regimes.",
                "No credentials, account IDs, raw order IDs, or raw log contents are exported.",
            ],
            "execution_authorized": False,
        }
        output_json = ROOT / "artifacts" / f"{OUTPUT_PREFIX}.json"
        output_parquet = ROOT / "artifacts" / f"{OUTPUT_PREFIX}.parquet"
        output_sha = ROOT / "artifacts" / f"{OUTPUT_PREFIX}.sha256"
        if frame.height:
            frame.write_parquet(output_parquet, compression="zstd")
        output_json.write_text(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        manifest_lines = []
        for name, path in (("json", output_json), ("parquet", output_parquet)):
            if path.exists():
                manifest_lines.append(f"{sha256_file(path)}  {path.name}")
        output_sha.write_text("\n".join(manifest_lines) + "\n", encoding="ascii")
        print(json.dumps({
            "account_is_demo": True,
            "orders_submitted_by_this_script": 0,
            "deal_history_rows_in_window": len(deals),
            "matched_order_completion_records": len(matched_completed),
            "observations": len(observations),
            "offset_seconds": offset,
            "by_symbol_and_order_type": by_symbol,
            "output_json": str(output_json.relative_to(ROOT)),
            "output_parquet": str(output_parquet.relative_to(ROOT)) if frame.height else None,
            "execution_authorized": False,
        }, indent=2))
        return payload
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    run()
