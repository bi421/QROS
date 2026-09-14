"""Strict Market Memory execution with canonical dataset provenance binding.

This module keeps the existing statistical pipeline unchanged while enforcing
strict dataset identity at the evidence publication boundary.  It also binds
the real-data production report to an explicit, validated numerical backend.
"""

from __future__ import annotations

import hashlib
from typing import Any

from researchos.data_engine.candle import Candle
from researchos.data_engine.dataset import HistoricalDataset
from researchos.market_memory.evidence import create_evidence_record
from researchos.market_memory.event_schema import EvidenceRecord, MarketMemoryReport
from researchos.market_memory.pipeline_v1 import run_market_memory_pipeline
from researchos.market_memory.production_quant_backend import (
    run_production_quant_backend_audit,
)
from researchos.research_identity import DatasetIdentity


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_dataset_identity(
    df: Any,
    *,
    data_path: str,
    asset: str,
    timeframe: str,
) -> DatasetIdentity:
    """Build canonical record/content and metadata hashes from validated D1 data."""
    candles: list[Candle] = []
    for row in df.iter_rows(named=True):
        candles.append(
            Candle(
                symbol=asset,
                timeframe=timeframe,
                timestamp=row["timestamp"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0) or 0.0),
                spread=(float(row["spread"]) if row.get("spread") is not None else None),
                tick_volume=(float(row["tick_volume"]) if row.get("tick_volume") is not None else None),
                real_volume=(float(row["real_volume"]) if row.get("real_volume") is not None else None),
            )
        )

    dataset = HistoricalDataset(
        symbol=asset,
        timeframe=timeframe,
        data_type="candle",
        records=candles,
        source="MT5",
        quality="Validated",
        version="1.0.0",
    )
    dataset.mark_ready()
    dataset.mark_validated()

    dataset_id = f"{asset}_{timeframe}_{_file_sha256(data_path)}"
    return DatasetIdentity(
        dataset_id=dataset_id,
        dataset_content_hash=dataset.dataset_content_hash,
        dataset_hash=dataset.dataset_hash,
    )


def _strict_record(record: EvidenceRecord, identity: DatasetIdentity) -> EvidenceRecord:
    """Re-emit an existing finding through the strict evidence constructor."""
    uncertainty = dict(record.uncertainty)
    uncertainty.pop("provenance", None)
    return create_evidence_record(
        finding_name=record.finding_name,
        dataset_id=identity.dataset_id,
        dataset_version=identity.dataset_hash,
        event_definition=record.event_definition,
        condition_definition=record.condition_definition,
        sample_size=record.sample_size,
        time_range=record.time_range,
        computation_method=record.computation_method,
        code_module=record.code_module,
        statistical_method=record.statistical_method,
        result=dict(record.result),
        uncertainty=uncertainty,
        validation_method=record.validation_method,
        random_seed=record.random_seed,
        status=record.status,
        dataset_identity=identity,
        dataset_content_hash=identity.dataset_content_hash,
        dataset_hash=identity.dataset_hash,
    )


def run_strict_market_memory_pipeline(
    data_path: str,
    *,
    asset: str = "XAUUSD",
    timeframe: str = "D1",
    fast_period: int = 20,
    slow_period: int = 100,
    seed: int = 42,
    minimum_events: int = 100,
    require_cpp: bool = True,
) -> MarketMemoryReport:
    """Run Market Memory with strict provenance and certified C++ quant execution.

    Event extraction and evidence methodology remain unchanged.  The production
    numerical boundary independently computes daily returns and descriptive
    statistics through BackendRouter -> CppQuantAdapter and records the exact
    backend metadata in the report.  With ``require_cpp=True`` the boundary
    fails closed rather than silently falling back to Python.
    """
    from researchos.market_memory.event_extractor import load_xauusd_d1

    df = load_xauusd_d1(data_path)
    identity = _build_dataset_identity(
        df,
        data_path=data_path,
        asset=asset,
        timeframe=timeframe,
    )

    closes = [float(value) for value in df.get_column("close").to_list()]
    quant_audit = run_production_quant_backend_audit(
        closes,
        require_cpp=require_cpp,
    )

    report = run_market_memory_pipeline(
        data_path=data_path,
        asset=asset,
        timeframe=timeframe,
        fast_period=fast_period,
        slow_period=slow_period,
        seed=seed,
        enforce_production_gate=True,
        minimum_events=minimum_events,
    )

    outcomes = dict(report.outcomes)
    outcomes["production_quant_backend"] = quant_audit.to_dict()

    if not report.evidence_records:
        return MarketMemoryReport(
            report_id=report.report_id,
            asset=report.asset,
            timeframe=report.timeframe,
            event_type=report.event_type,
            generated_at=report.generated_at,
            total_events=report.total_events,
            date_range=report.date_range,
            outcomes=outcomes,
            conditional_results=report.conditional_results,
            validation_results=report.validation_results,
            evidence_records=[],
            self_audit=report.self_audit,
            overall_status=report.overall_status,
            notes=(
                report.notes
                + f" Strict dataset identity bound: {identity.to_dict()}"
                + f" Production quant backend: {quant_audit.to_dict()}"
            ),
        )

    strict_records = [_strict_record(record, identity) for record in report.evidence_records]
    return MarketMemoryReport(
        report_id=report.report_id,
        asset=report.asset,
        timeframe=report.timeframe,
        event_type=report.event_type,
        generated_at=report.generated_at,
        total_events=report.total_events,
        date_range=report.date_range,
        outcomes=outcomes,
        conditional_results=report.conditional_results,
        validation_results=report.validation_results,
        evidence_records=strict_records,
        self_audit=report.self_audit,
        overall_status=report.overall_status,
        notes=(
            report.notes
            + f" Strict dataset identity bound: {identity.to_dict()}"
            + f" Production quant backend: {quant_audit.to_dict()}"
        ),
    )


__all__ = ["run_strict_market_memory_pipeline"]
