"""Tests for strict Market Memory provenance and Probability integration."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl
import pytest

from researchos.market_memory.decision_adapter import market_memory_to_probability
from researchos.market_memory.event_schema import EvidenceRecord, EvidenceStatus, MarketMemoryReport
from researchos.market_memory.strict_pipeline import _build_dataset_identity, _strict_record


def _sample_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": pl.datetime_range(
                start=datetime(2025, 1, 1),
                end=datetime(2025, 1, 3),
                interval="1d",
                eager=True,
            ),
            "open": [100.0, 101.0, 102.0],
            "high": [102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0],
            "close": [101.0, 102.0, 103.0],
            "volume": [10.0, 11.0, 12.0],
        }
    )


def _record(dataset_id: str) -> EvidenceRecord:
    return EvidenceRecord(
        finding_id="legacy-finding",
        finding_name="SMA Crossover bullish_crossover",
        dataset_id=dataset_id,
        dataset_version="legacy",
        event_definition="SMA20/100 crossover",
        condition_definition="{'direction': 'bullish'}",
        sample_size=100,
        time_range=("2025-01-01T00:00:00", "2025-04-10T00:00:00"),
        computation_method="forward_return_analysis",
        code_module="test",
        statistical_method="wilson",
        random_seed=42,
        validation_method="walk_forward_expanding_purged",
        result={"raw_probability": 0.70, "mean_return": 0.01, "std_return": 0.02},
        status=EvidenceStatus.VALIDATED.value,
    )


def test_strict_record_rebinds_legacy_dataset_id_to_exact_identity(tmp_path: Path) -> None:
    source = tmp_path / "sample.csv"
    source.write_text("sample-data", encoding="utf-8")
    identity = _build_dataset_identity(
        _sample_df(), data_path=str(source), asset="XAUUSD", timeframe="D1"
    )

    legacy_dataset_id = f"XAUUSD_D1_{identity.dataset_id.rsplit('_', 1)[-1][:16]}"
    record = _strict_record(_record(legacy_dataset_id), identity)
    persisted = record.uncertainty["provenance"]["dataset_identity"]

    assert record.dataset_id == identity.dataset_id
    assert persisted["dataset_id"] == identity.dataset_id
    assert persisted["dataset_content_hash"] == identity.dataset_content_hash
    assert persisted["dataset_hash"] == identity.dataset_hash
    assert record.dataset_version == identity.dataset_hash


def test_strict_market_memory_evidence_reaches_probability() -> None:
    report = MarketMemoryReport(
        report_id="report-1",
        asset="XAUUSD",
        timeframe="D1",
        event_type="SMA_CROSSOVER",
        evidence_records=[
            EvidenceRecord(
                finding_id="bullish",
                finding_name="bullish",
                dataset_id="dataset-1",
                dataset_version="hash-1",
                event_definition="sma",
                condition_definition="{'direction': 'bullish'}",
                sample_size=100,
                time_range=("2025-01-01", "2025-04-10"),
                computation_method="forward_return_analysis",
                code_module="test",
                statistical_method="wilson",
                result={"raw_probability": 0.70},
                status=EvidenceStatus.VALIDATED.value,
            ),
            EvidenceRecord(
                finding_id="bearish",
                finding_name="bearish",
                dataset_id="dataset-1",
                dataset_version="hash-1",
                event_definition="sma",
                condition_definition="{'direction': 'bearish'}",
                sample_size=100,
                time_range=("2025-01-01", "2025-04-10"),
                computation_method="forward_return_analysis",
                code_module="test",
                statistical_method="wilson",
                result={"raw_probability": 0.40},
                status=EvidenceStatus.VALIDATED.value,
            ),
        ],
    )

    assessment = market_memory_to_probability(report, decision_context_id="ctx-1")

    assert assessment.sample_size == 2
    assert assessment.bullish_probability > assessment.bearish_probability
    assert assessment.bullish_probability + assessment.bearish_probability + assessment.neutral_probability == pytest.approx(1.0)
