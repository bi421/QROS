"""Audit XAUUSD M1 signal-event returns under observed spread and slippage stress.

This is a research diagnostic, not a broker simulator. It uses the local MT5
bar dataset's recorded spread points, enters on the next available bar open,
exits at the source event's realized_end_1d close, and fails closed on dataset
identity mismatches. Event-level overlapping returns are reported separately
from a non-overlapping 1-day holding diagnostic. Commissions, financing, market
impact, and live execution latency are not modeled.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DATA = Path("data/mt5/xauusd/XAUUSD_M1_2021_2025_MT5.csv")
DEFAULT_SOURCE = Path("artifacts/xauusd_m1_real_events_outcomes.json")
DEFAULT_OUTPUT = Path("artifacts/xauusd_m1_edge_cost_audit.json")
POINT_SIZE = 0.01
MAX_ENTRY_GAP_SECONDS = 300
SLIPPAGE_POINTS_PER_SIDE = (0, 1, 2, 5, 10)


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must be timezone-aware: {value}")
    return parsed.astimezone(timezone.utc)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _score(
    returns: list[float], *, include_compounding: bool = True
) -> dict[str, float | int | str | None]:
    if not returns:
        return {
            "trade_count": 0,
            "mean_return_pct": None,
            "median_return_pct": None,
            "win_rate_pct": None,
            "profit_factor": None,
            "compounded_return_pct": None,
        }
    positive = sum(value for value in returns if value > 0)
    negative = -sum(value for value in returns if value < 0)
    compounded = math.prod(1.0 + value for value in returns) - 1.0 if include_compounding else None
    return {
        "trade_count": len(returns),
        "mean_return_pct": round(sum(returns) / len(returns) * 100.0, 8),
        "median_return_pct": round(statistics.median(returns) * 100.0, 8),
        "win_rate_pct": round(sum(value > 0 for value in returns) / len(returns) * 100.0, 8),
        "profit_factor": round(positive / negative, 8)
        if negative > 0
        else (None if positive == 0 else "INF"),
        "compounded_return_pct": round(compounded * 100.0, 8) if compounded is not None else None,
    }


def _bootstrap_mean_ci(
    values: list[float], seed: int = 20261015, samples: int = 10000
) -> list[float] | None:
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    count = len(values)
    means = sorted(
        sum(values[rng.randrange(count)] for _ in range(count)) / count for _ in range(samples)
    )
    return [
        round(means[int(0.025 * (samples - 1))] * 10000.0, 8),
        round(means[int(0.975 * (samples - 1))] * 10000.0, 8),
    ]


def _fill_returns(
    row: dict[str, Any], direction: int, slippage_points: int
) -> tuple[float, float, float]:
    entry = float(row["entry_open"])
    exit_price = float(row["exit_close"])
    entry_spread = float(row["entry_spread"]) * POINT_SIZE
    exit_spread = float(row["exit_spread"]) * POINT_SIZE
    slip = slippage_points * POINT_SIZE

    if direction == 1:
        entry_fill = entry + entry_spread + slip
        exit_fill = exit_price - slip
        signal_return = (exit_fill - entry_fill) / entry_fill
    elif direction == -1:
        entry_fill = entry - slip
        exit_fill = exit_price + exit_spread + slip
        signal_return = (entry_fill - exit_fill) / entry_fill
    else:
        raise ValueError("direction must be +1 or -1")

    long_return = (exit_price - entry - entry_spread - 2 * slip) / (entry + entry_spread + slip)
    short_return = (entry - exit_price - exit_spread - 2 * slip) / max(entry - slip, 1e-12)
    return signal_return, long_return, short_return


def audit(
    source_path: Path, data_path: Path, walkforward_path: Path | None = None
) -> dict[str, Any]:
    source_raw = source_path.read_bytes()
    source = json.loads(source_raw.decode("utf-8"))
    walkforward_raw = walkforward_path.read_bytes() if walkforward_path else None
    walkforward = json.loads(walkforward_raw.decode("utf-8")) if walkforward_raw else None
    contract = source.get("contract", {})
    dataset = source.get("dataset", {})
    if (contract.get("asset"), contract.get("timeframe"), contract.get("label")) != (
        "XAUUSD",
        "M1",
        "hit_threshold_1d",
    ):
        raise ValueError("Unexpected source research contract")
    expected_sha = dataset.get("sha256")
    actual_sha = _sha256(data_path)
    if not isinstance(expected_sha, str) or actual_sha != expected_sha:
        raise ValueError(
            f"Dataset SHA-256 mismatch: source declares {expected_sha!r}, actual is {actual_sha}"
        )

    holdout_ids: set[str] | None = None
    if walkforward is not None:
        if walkforward.get("stage") != "M1_WALK_FORWARD_RAW_PROBABILITY":
            raise ValueError("Walk-forward artifact has an unexpected stage")
        if (
            walkforward.get("source_artifact", {}).get("sha256")
            != hashlib.sha256(source_raw).hexdigest()
        ):
            raise ValueError("Walk-forward artifact is not bound to the supplied source SHA-256")
        holdout = walkforward.get("holdout")
        if not isinstance(holdout, dict) or not isinstance(holdout.get("predictions"), list):
            raise ValueError("Walk-forward artifact is missing final holdout predictions")
        holdout_ids = {item.get("event_id") for item in holdout["predictions"]}
        if not holdout_ids or None in holdout_ids:
            raise ValueError("Walk-forward final holdout has invalid event IDs")

    events: list[dict[str, Any]] = []
    event_times: set[datetime] = set()
    exit_times: set[datetime] = set()
    seen_ids: set[str] = set()
    skipped: dict[str, int] = {}
    for event in source.get("events_data", []):
        outcome = event.get("outcome") or {}
        availability = outcome.get("data_availability") or {}
        end_value = availability.get("realized_end_1d")
        ret_value = outcome.get("return_1d")
        if end_value is None or ret_value in (None, "FIELD_UNAVAILABLE"):
            continue
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id or event_id in seen_ids:
            raise ValueError(f"Missing or duplicate event_id: {event_id!r}")
        direction_text = event.get("event_direction") or event.get("direction")
        if direction_text not in {"bullish", "bearish"}:
            # Existing event artifacts encode direction in the event ID.
            direction_text = (
                "bullish"
                if event_id.endswith("_bullish")
                else ("bearish" if event_id.endswith("_bearish") else None)
            )
        if direction_text not in {"bullish", "bearish"}:
            raise ValueError(f"Missing signal direction for {event_id}")
        timestamp = _time(event["timestamp"])
        realized_end = _time(end_value)
        if realized_end <= timestamp:
            raise ValueError(f"Outcome endpoint must follow event timestamp: {event_id}")
        event_price = _finite_number(event.get("event_price"), f"{event_id}.event_price")
        underlying_return = _finite_number(ret_value, f"{event_id}.return_1d")
        if not math.isfinite(event_price) or event_price <= 0:
            raise ValueError(f"Invalid event price: {event_id}")
        direction = 1 if direction_text == "bullish" else -1
        events.append(
            {
                "event_id": event_id,
                "timestamp": timestamp,
                "realized_end": realized_end,
                "direction": direction,
                "event_price": event_price,
                "source_return_1d": underlying_return,
            }
        )
        event_times.add(timestamp)
        exit_times.add(realized_end)
        seen_ids.add(event_id)

    if not events:
        raise ValueError("No complete, direction-labelled events available")

    # One streaming pass: retain only the next bar after each signal and each
    # source-defined realized endpoint. Never fabricate missing bars.
    entries: dict[datetime, dict[str, Any]] = {}
    exits: dict[datetime, dict[str, Any]] = {}
    signal_closes: dict[datetime, float] = {}
    previous_time: datetime | None = None
    with data_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"time", "open", "close", "spread"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"Dataset missing required columns: {sorted(required)}")
        for raw in reader:
            current_time = _time(raw["time"])
            if current_time in event_times:
                signal_closes[current_time] = float(raw["close"])
            if previous_time in event_times and previous_time not in entries:
                entries[previous_time] = {
                    "entry_time": current_time,
                    "entry_open": float(raw["open"]),
                    "entry_spread": int(raw["spread"]),
                }
            if current_time in exit_times:
                exits[current_time] = {
                    "exit_close": float(raw["close"]),
                    "exit_spread": int(raw["spread"]),
                }
            previous_time = current_time

    rows: list[dict[str, Any]] = []
    for event in events:
        signal_close = signal_closes.get(event["timestamp"])
        entry = entries.get(event["timestamp"])
        exit_row = exits.get(event["realized_end"])
        if signal_close is None:
            skipped["missing_signal_bar"] = skipped.get("missing_signal_bar", 0) + 1
            continue
        if abs(signal_close - event["event_price"]) > 1e-6:
            raise ValueError(
                f"Source event price does not match source dataset close: {event['event_id']}"
            )
        if exit_row is not None:
            recomputed_return = float(exit_row["exit_close"]) / event["event_price"] - 1.0
            if abs(recomputed_return - event["source_return_1d"]) > 1e-9:
                raise ValueError(
                    f"Source return_1d does not recompute from dataset: {event['event_id']}"
                )
        if entry is None:
            skipped["no_next_bar"] = skipped.get("no_next_bar", 0) + 1
            continue
        if exit_row is None:
            skipped["missing_realized_endpoint_bar"] = (
                skipped.get("missing_realized_endpoint_bar", 0) + 1
            )
            continue
        gap = (entry["entry_time"] - event["timestamp"]).total_seconds()
        if gap <= 0 or gap > MAX_ENTRY_GAP_SECONDS:
            skipped["entry_gap_over_5m"] = skipped.get("entry_gap_over_5m", 0) + 1
            continue
        if entry["entry_open"] <= 0 or exit_row["exit_close"] <= 0:
            skipped["invalid_price"] = skipped.get("invalid_price", 0) + 1
            continue
        row = {**event, **entry, **exit_row}
        row["entry_gap_seconds"] = gap
        row["gross_signal_return"] = (
            event["direction"] * (row["exit_close"] - row["entry_open"]) / row["entry_open"]
        )
        rows.append(row)

    rows.sort(key=lambda row: (row["timestamp"], row["event_id"]))

    def _non_overlapping(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        last_exit: datetime | None = None
        for item in items:
            if last_exit is None or item["entry_time"] >= last_exit:
                selected.append(item)
                last_exit = item["realized_end"]
        return selected

    def _scenario(
        items: list[dict[str, Any]],
        slip_points: int,
        include_uncertainty: bool = False,
        include_compounding: bool = True,
    ) -> dict[str, Any]:
        signal_returns: list[float] = []
        long_returns: list[float] = []
        short_returns: list[float] = []
        delta_vs_long: list[float] = []
        delta_vs_short: list[float] = []
        for item in items:
            signal_ret, long_ret, short_ret = _fill_returns(item, item["direction"], slip_points)
            signal_returns.append(signal_ret)
            long_returns.append(long_ret)
            short_returns.append(short_ret)
            delta_vs_long.append(signal_ret - long_ret)
            delta_vs_short.append(signal_ret - short_ret)
        return {
            "signal_direction": _score(signal_returns, include_compounding=include_compounding),
            "always_long_baseline": _score(long_returns, include_compounding=include_compounding),
            "always_short_baseline": _score(short_returns, include_compounding=include_compounding),
            "mean_signal_minus_best_directional_baseline_bps": round(
                (
                    sum(signal_returns) / len(signal_returns)
                    - max(
                        sum(long_returns) / len(long_returns),
                        sum(short_returns) / len(short_returns),
                    )
                )
                * 10000.0,
                8,
            )
            if signal_returns
            else None,
            "paired_delta_vs_always_long_bps": round(
                sum(delta_vs_long) / len(delta_vs_long) * 10000.0, 8
            )
            if delta_vs_long
            else None,
            "paired_delta_vs_always_long_bootstrap_95ci_bps": (
                _bootstrap_mean_ci(delta_vs_long) if include_uncertainty else None
            ),
            "paired_win_rate_vs_always_long_pct": round(
                sum(value > 0 for value in delta_vs_long) / len(delta_vs_long) * 100.0, 8
            )
            if delta_vs_long
            else None,
            "paired_delta_vs_always_short_bps": round(
                sum(delta_vs_short) / len(delta_vs_short) * 10000.0, 8
            )
            if delta_vs_short
            else None,
        }

    non_overlapping = _non_overlapping(rows)
    holdout_rows: list[dict[str, Any]] = []
    missing_holdout_ids: set[str] = set()
    if holdout_ids is not None:
        source_event_ids = {event["event_id"] for event in events}
        if not holdout_ids.issubset(source_event_ids):
            raise ValueError(
                "Walk-forward holdout contains event IDs absent from the source artifact"
            )
        row_ids = {row["event_id"] for row in rows}
        missing_holdout_ids = holdout_ids - row_ids
        holdout_rows = [row for row in rows if row["event_id"] in holdout_ids]
    holdout_non_overlapping = _non_overlapping(holdout_rows)

    scenarios = []
    for slip_points in SLIPPAGE_POINTS_PER_SIDE:
        scenarios.append(
            {
                "slippage_points_per_side": slip_points,
                "spread_source": "observed MT5 bar spread at entry/exit; points × 0.01 USD",
                "commission_model": "excluded; broker commission not present in source dataset",
                "full_history_overlapping_event_diagnostic": _scenario(
                    rows, slip_points, include_compounding=False
                ),
                "full_history_non_overlapping_1d_diagnostic": _scenario(
                    non_overlapping, slip_points
                ),
                "final_holdout_non_overlapping_1d_diagnostic": _scenario(
                    holdout_non_overlapping, slip_points, include_uncertainty=True
                )
                if holdout_ids is not None
                else None,
            }
        )

    return {
        "schema": "xauusd-m1-edge-cost-audit.v1",
        "status": "COMPUTED_RESEARCH_DIAGNOSTIC_NOT_EDGE_CERTIFICATION",
        "source_artifact": {
            "path": str(source_path),
            "sha256": hashlib.sha256(source_raw).hexdigest(),
            "complete_directional_events": len(events),
        },
        "dataset": {
            "path": str(data_path),
            "sha256": actual_sha,
            "expected_sha256": expected_sha,
            "identity_verified": True,
            "point_size_usd": POINT_SIZE,
            "spread_column_units": "MT5 points",
        },
        "methodology": {
            "entry": "next available M1 bar open after signal timestamp",
            "exit": "source-defined realized_end_1d M1 bar close",
            "direction": "signal direction from event ID / explicit direction field",
            "costs": "observed entry/exit spread plus deterministic slippage stress per side",
            "slippage_scenarios_points_per_side": list(SLIPPAGE_POINTS_PER_SIDE),
            "excluded_costs": [
                "commission",
                "financing/swap",
                "market impact",
                "latency beyond next-bar entry",
            ],
            "non_overlapping_rule": "entry_time >= prior selected event realized_end_1d",
            "overlapping_event_compounding": "not computed because overlapping event returns are not a portfolio equity curve",
            "limitations": [
                "event-level results are not a broker-executable portfolio backtest",
                "non-overlapping diagnostic is an idealized fixed-horizon event study",
                "slippage values are stress assumptions, not measured historical fills",
                "always-long/short baselines use the same event timestamps, holding windows, and cost assumptions",
            ],
        },
        "walkforward_holdout": {
            "provided": walkforward is not None,
            "artifact_sha256": hashlib.sha256(walkforward_raw).hexdigest()
            if walkforward_raw
            else None,
            "holdout_prediction_count": len(holdout_ids) if holdout_ids is not None else None,
            "holdout_events_with_cost_inputs": len(holdout_rows)
            if holdout_ids is not None
            else None,
            "holdout_events_missing_cost_inputs": len(missing_holdout_ids)
            if holdout_ids is not None
            else None,
            "missing_holdout_event_ids": sorted(missing_holdout_ids)
            if holdout_ids is not None
            else None,
            "coverage_status": (
                "COMPLETE" if not missing_holdout_ids else "PARTIAL_EXCLUSIONS_REPORTED"
            )
            if holdout_ids is not None
            else "NOT_RUN",
            "holdout_non_overlapping_events": len(holdout_non_overlapping)
            if holdout_ids is not None
            else None,
        },
        "counts": {
            "complete_source_events": len(events),
            "events_with_entry_and_exit_bars": len(rows),
            "non_overlapping_events": len(non_overlapping),
            "skipped": skipped,
        },
        "scenarios": scenarios,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument(
        "--walkforward", type=Path, default=Path("artifacts/xauusd_m1_walkforward.json")
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = audit(args.source, args.data, args.walkforward)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "dataset_sha256": report["dataset"]["sha256"],
                "counts": report["counts"],
                "walkforward_holdout": report["walkforward_holdout"],
                "scenarios": [
                    {
                        "slippage_points_per_side": scenario["slippage_points_per_side"],
                        "final_holdout_non_overlapping": scenario[
                            "final_holdout_non_overlapping_1d_diagnostic"
                        ],
                    }
                    for scenario in report["scenarios"]
                ],
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
