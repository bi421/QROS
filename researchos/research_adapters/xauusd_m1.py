"""Bind the frozen XAUUSD M1 pipeline to the application-neutral core.

This module is deliberately outside ``research_core``.  It knows how to resolve
raw dataset bytes and how to call the existing frozen research stages; the core
only receives immutable contracts and content-addressed output metadata.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

import polars as pl

from researchos.orchestration.xauusd_cost_model import calculate_trade_costs, load_cost_config
from researchos.research_core.contracts import ResearchRequest
from researchos.research_core.runner import PipelineArtifact
from researchos.evaluation.research_run_metrics import evaluate_xauusd_m1_run
from researchos.orchestration.qros_research_controls import (
    QROS_RESEARCH_CONTROLS_VERSION,
    build_audit_record,
    unified_research_gate,
)
from scripts.run_xauusd_m1_oos_calibration import run as run_calibration
from scripts.run_xauusd_m1_real_pipeline import run as run_real_pipeline
from scripts.run_xauusd_m1_walkforward import run as run_walkforward


class RawDatasetResolver(Protocol):
    """Resolve the exact raw bytes identified by a ResearchDataset."""

    def __call__(self, request: ResearchRequest) -> bytes:
        """Return raw dataset bytes for the requested dataset."""


def _build_costed_event_trades(raw: bytes, events: list[dict], dataset_sha256: str) -> pl.DataFrame:
    """Create next-bar-entry/one-day-exit trade rows with bar-level spread costs."""
    import io
    from datetime import datetime

    config = load_cost_config()
    frame = pl.read_csv(io.BytesIO(raw), try_parse_dates=False).rename(
        {"time": "timestamp", "tick_volume": "volume"}
    )
    frame = frame.with_columns(
        pl.col("timestamp").str.to_datetime(strict=True, time_zone="UTC"),
        *[pl.col(name).cast(pl.Float64) for name in ("open", "high", "low", "close", "spread")],
    ).sort("timestamp")
    frame = frame.with_columns(
        pl.max_horizontal(
            pl.col("high") - pl.col("low"),
            (pl.col("high") - pl.col("close").shift(1)).abs(),
            (pl.col("low") - pl.col("close").shift(1)).abs(),
        ).alias("_tr")
    ).with_columns(pl.col("_tr").rolling_mean(window_size=14, min_samples=14).alias("_atr14"))
    timestamps = frame["timestamp"].to_list()
    lookup = {timestamp: index for index, timestamp in enumerate(timestamps)}
    rows: list[dict] = []
    for event in events:
        try:
            event_ts = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            event_index = lookup[event_ts]
            entry_index = event_index + 1
            exit_value = event.get("outcome", {}).get("data_availability", {}).get("realized_end_1d")
            if not exit_value:
                continue
            exit_ts = datetime.fromisoformat(exit_value.replace("Z", "+00:00"))
            exit_index = lookup[exit_ts]
            entry = frame.row(entry_index, named=True)
            exit_row = frame.row(exit_index, named=True)
            if entry["_atr14"] is None or exit_row["_atr14"] is None:
                continue
            direction = 1 if event["direction"].lower() in {"bullish", "long", "up"} else -1
            row = {
                "trade_id": hashlib.sha256(f"{dataset_sha256}|{event['event_id']}|nextbar-1d".encode()).hexdigest(),
                "event_id": event["event_id"], "dataset_sha256": dataset_sha256,
                "signal_ts": event_ts, "entry_ts": entry["timestamp"], "exit_ts": exit_row["timestamp"],
                "direction": direction, "entry_price": entry["open"], "exit_price": exit_row["close"],
                "entry_spread": entry["spread"], "exit_spread": exit_row["spread"],
                "entry_atr": entry["_atr14"], "exit_atr": exit_row["_atr14"],
            }
            for multiplier in (0.5, 1.0, 1.5, 2.0):
                costs = calculate_trade_costs(
                    entry_price=row["entry_price"], exit_price=row["exit_price"], direction=direction,
                    entry_spread_points=row["entry_spread"], exit_spread_points=row["exit_spread"],
                    entry_atr=row["entry_atr"], exit_atr=row["exit_atr"],
                    config=config, cost_multiplier=multiplier,
                )
                for key in ("gross_return", "spread_cost_return", "commission_cost_return",
                            "slippage_cost_return", "total_cost_return", "net_return",
                            "cost_basis_declared", "costs_verified"):
                    row[f"{key}_x{multiplier:g}"] = costs.get(key)
            rows.append(row)
        except (KeyError, ValueError, IndexError):
            continue
    return pl.DataFrame(rows) if rows else pl.DataFrame({
        "trade_id": [], "signal_ts": [], "entry_ts": [], "exit_ts": [],
        "gross_return_x1": [], "net_return_x1": [],
    })


class FrozenXauusdM1Pipeline:
    """Execute the existing frozen XAUUSD M1 stages without changing them."""

    def __init__(self, resolver: RawDatasetResolver) -> None:
        self._resolver = resolver

    def __call__(self, request: ResearchRequest) -> Iterable[PipelineArtifact]:
        raw = self._resolver(request)
        actual_sha256 = hashlib.sha256(raw).hexdigest()
        if actual_sha256 != request.dataset.content_sha256:
            raise ValueError(
                "resolved raw dataset SHA-256 does not match the ResearchDataset provenance"
            )

        with tempfile.TemporaryDirectory(prefix="researchos-xauusd-m1-") as temp_dir:
            root = Path(temp_dir)
            source_path = root / "xauusd_m1_mt5.csv"
            real_path = root / "xauusd_m1_real_events_outcomes.json"
            walkforward_path = root / "xauusd_m1_walkforward.json"
            calibration_path = root / "xauusd_m1_oos_calibration.json"
            metrics_path = root / "xauusd_m1_meta_evaluation.json"
            source_path.write_bytes(raw)

            run_real_pipeline(source_path, real_path, threshold=0.0)
            run_walkforward(
                real_path,
                walkforward_path,
                train_size=2000,
                validation_size=500,
                step_size=500,
            )
            run_calibration(real_path, walkforward_path, calibration_path)

            real_bytes = real_path.read_bytes()
            walkforward_bytes = walkforward_path.read_bytes()
            calibration_bytes = calibration_path.read_bytes()
            real_report = json.loads(real_bytes)
            costed_trades_path = root / "xauusd_m1_costed_trades.parquet"
            costed_trades = _build_costed_event_trades(
                raw, real_report.get("events_data", []), request.dataset.content_sha256
            )
            costed_trades.write_parquet(costed_trades_path, compression="zstd")
            costed_trades_sha256 = hashlib.sha256(costed_trades_path.read_bytes()).hexdigest()
            meta_metrics = evaluate_xauusd_m1_run(real_bytes, walkforward_bytes, calibration_bytes)
            meta_metrics["costed_trade_artifact"] = {
                "sha256": costed_trades_sha256,
                "trade_count": costed_trades.height,
                "cost_basis_declared": bool(costed_trades.height and costed_trades["cost_basis_declared_x1"][0]),
                "costs_verified": False,
                "commission_and_slippage_source": "EXPLICIT_ASSUMPTIONS_NOT_BROKER_VERIFIED",
                "execution_authorized": False,
            }

            # The frozen M1 workflow currently has no verified spread/commission/slippage
            # evidence. Invoke the gate fail-closed; do not mislabel gross event returns as net.
            cost_metadata = {
                "cost_source": "MT5_BAR_LEVEL_SPREAD_PLUS_EXPLICIT_COST_ASSUMPTIONS",
                "cost_units": "XAUUSD_PRICE_RETURN; SPREAD_POINTS_CONVERTED_USING_SYMBOL_POINT",
                "commission_model": "ASSUMED_7_USD_PER_LOT_ROUND_TURN",
                "slippage_model": "ASSUMED_0.05_ATR_PER_SIDE",
                "spread_log_sha256": request.dataset.content_sha256,
                "spread_observation_count": int(real_report.get("dataset", {}).get("rows") or 0),
                "net_return_definition": "NET_OF_SPREAD_COMMISSION_SLIPPAGE",
                "all_in_costs_verified": False,
            }
            gate_decision = unified_research_gate(
                trade_returns=None,
                fold_returns=None,
                tested_trial_count=1,
                cost_metadata=cost_metadata,
            )
            meta_metrics["research_controls_version"] = QROS_RESEARCH_CONTROLS_VERSION
            meta_metrics["research_gate"] = gate_decision
            audit_record = build_audit_record(
                input_payload={
                    "dataset_sha256": request.dataset.content_sha256,
                    "dataset_rows_reported_by_engine": real_report.get("dataset", {}).get("rows"),
                    "dataset_row_metadata_count": len(request.dataset.rows),
                    "upstream_artifacts": {
                        "real_events_sha256": hashlib.sha256(real_bytes).hexdigest(),
                        "walkforward_sha256": hashlib.sha256(walkforward_bytes).hexdigest(),
                        "calibration_sha256": hashlib.sha256(calibration_bytes).hexdigest(),
                        "costed_trade_parquet_sha256": costed_trades_sha256,
                    },
                },
                decision=gate_decision,
                source_commit=os.environ.get("QROS_SOURCE_COMMIT", "UNDECLARED_RUNTIME_SOURCE_COMMIT"),
                config_version=QROS_RESEARCH_CONTROLS_VERSION,
            )
            meta_metrics["research_audit"] = audit_record
            metrics_path.write_text(
                json.dumps(meta_metrics, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False),
                encoding="utf-8",
            )

            outputs = (
                ("xauusd_m1_real_events", real_path),
                ("xauusd_m1_costed_trades", costed_trades_path),
                ("xauusd_m1_walkforward", walkforward_path),
                ("xauusd_m1_oos_calibration", calibration_path),
                ("xauusd_m1_meta_evaluation", metrics_path),
            )
            for kind, path in outputs:
                content = path.read_bytes()
                yield PipelineArtifact(
                    artifact_id=hashlib.sha256(content).hexdigest(),
                    kind=kind,
                    content=content,
                )


__all__ = ["FrozenXauusdM1Pipeline", "RawDatasetResolver"]
