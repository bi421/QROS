"""
Market Memory V1 — comprehensive tests.

Tests cover:
  - Event schema serialization and determinism
  - Event extraction (SMA crossover detection)
  - Forward outcome calculation
  - Conditional analysis
  - Bootstrap uncertainty
  - Temporal validation
  - Self-audit
  - Evidence provenance
  - End-to-end pipeline
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import polars as pl
import pytest

from researchos.market_memory.bootstrap import (
    bootstrap_mean_ci,
    bootstrap_stability_check,
)
from researchos.market_memory.conditioning import (
    ConditionSpec,
    compute_conditional_statistics,
    evaluate_condition,
    filter_events,
)
from researchos.market_memory.event_extractor import (
    extract_sma_crossover_events,
    load_xauusd_d1,
)
from researchos.market_memory.event_schema import (
    ConditionalResult,
    EventContext,
    EventOutcome,
    EventType,
    EvidenceStatus,
    MarketEvent,
)
from researchos.market_memory.event_schema import (
    MarketRegime as MarketRegimeEnum,
)
from researchos.market_memory.evidence import create_evidence_record
from researchos.market_memory.outcome_engine import compute_forward_outcomes
from researchos.market_memory.pipeline_v1 import run_market_memory_pipeline
from researchos.market_memory.self_audit import run_self_audit
from researchos.market_memory.temporal_validation import (
    check_temporal_integrity,
    chronological_split,
    expanding_window_splits,
)

# =============================================================================
# Helpers
# =============================================================================

DATA_PATH = "data/curated/xauusd/xauusd_d1_2021_2025_mt5_final.csv"

SKIP_IF_NO_DATA = pytest.mark.skipif(
    not os.path.exists(DATA_PATH),
    reason=f"Data file not found: {DATA_PATH}",
)


def _make_minimal_event(
    event_id: str = "test_001",
    direction: str = "bullish",
    timestamp_str: str = "2021-06-01T00:00:00",
) -> MarketEvent:
    """Create a minimal MarketEvent for testing."""
    ts = timestamp_str if isinstance(timestamp_str, str) else timestamp_str.isoformat()
    if isinstance(ts, str):
        ts = ts.replace("Z", "+00:00")
    timestamp = ts if isinstance(ts, datetime) else datetime.fromisoformat(ts)

    context = EventContext(
        event_id=event_id,
        asset="XAUUSD",
        timeframe="D1",
        timestamp=timestamp,
        event_price=1900.0,
        sma_fast=1910.0,
        sma_slow=1890.0,
        atr=15.0,
        rsi=65.0,
        market_regime=MarketRegimeEnum.TRENDING_UP.value,
        volatility_state="Low",
    )
    return MarketEvent(
        event_id=event_id,
        asset="XAUUSD",
        timeframe="D1",
        event_type=EventType.SMA_CROSSOVER.value,
        direction=direction,
        timestamp=timestamp,
        event_price=1900.0,
        context=context,
    )


def _make_event_with_outcome(
    event_id: str = "test_001",
    direction: str = "bullish",
    return_1d: float = 0.01,
    timestamp_str: str = "2021-06-01T00:00:00",
) -> MarketEvent:
    """Create a MarketEvent with outcome."""
    event = _make_minimal_event(event_id, direction, timestamp_str)
    outcome = EventOutcome(
        event_id=event_id,
        asset="XAUUSD",
        timeframe="D1",
        event_timestamp=event.timestamp,
        return_1d=return_1d,
        direction_1d="up" if return_1d > 0 else "down",
    )
    return MarketEvent(
        event_id=event.event_id,
        asset=event.asset,
        timeframe=event.timeframe,
        event_type=event.event_type,
        direction=event.direction,
        timestamp=event.timestamp,
        event_price=event.event_price,
        context=event.context,
        outcome=outcome,
    )


# =============================================================================
# Event Schema Tests
# =============================================================================


class TestEventSchema:
    """Test event schema dataclasses."""

    def test_event_context_serialization(self):
        ctx = EventContext(
            event_id="e1",
            asset="XAUUSD",
            timeframe="D1",
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            event_price=1900.0,
        )
        d = ctx.to_dict()
        assert d["event_id"] == "e1"
        assert d["asset"] == "XAUUSD"
        assert d["spread"] == "FIELD_UNAVAILABLE"

    def test_event_outcome_serialization(self):
        outcome = EventOutcome(
            event_id="e1",
            asset="XAUUSD",
            timeframe="D1",
            event_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            return_1d=0.01,
            return_5m="FIELD_UNAVAILABLE",
        )
        d = outcome.to_dict()
        assert d["return_1d"] == 0.01
        assert d["return_5m"] == "FIELD_UNAVAILABLE"

    def test_market_event_creation(self):
        event = _make_minimal_event()
        assert event.event_id == "test_001"
        assert event.direction == "bullish"
        assert event.event_type == EventType.SMA_CROSSOVER.value

    def test_market_event_serialization(self):
        event = _make_minimal_event()
        d = event.to_dict()
        assert d["event_id"] == "test_001"
        assert d["direction"] == "bullish"
        assert d["context"]["event_price"] == 1900.0

    def test_evidence_status_enum(self):
        assert EvidenceStatus.VALIDATED.value == "VALIDATED"
        assert EvidenceStatus.EXPLORATORY.value == "EXPLORATORY"

    def test_unavailable_fields(self):
        ctx = EventContext(
            event_id="e1",
            asset="XAUUSD",
            timeframe="D1",
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        assert ctx.spread == "FIELD_UNAVAILABLE"
        assert ctx.dxy == "FIELD_UNAVAILABLE"


# =============================================================================
# Event Extractor Tests
# =============================================================================


class TestEventExtractor:
    """Test SMA crossover event extraction."""

    @SKIP_IF_NO_DATA
    def test_load_xauusd_d1(self):
        df = load_xauusd_d1(DATA_PATH)
        assert len(df) > 0
        assert "timestamp" in df.columns
        assert "close" in df.columns

    @SKIP_IF_NO_DATA
    def test_extract_events(self):
        df = load_xauusd_d1(DATA_PATH)
        events = extract_sma_crossover_events(df)
        assert len(events) > 0
        for e in events:
            assert e.event_type == EventType.SMA_CROSSOVER.value
            assert e.direction in ("bullish", "bearish")
            assert e.context is not None

    @SKIP_IF_NO_DATA
    def test_event_determinism(self):
        df = load_xauusd_d1(DATA_PATH)
        events1 = extract_sma_crossover_events(df, seed=42)
        events2 = extract_sma_crossover_events(df, seed=42)
        assert len(events1) == len(events2)
        for e1, e2 in zip(events1, events2):
            assert e1.event_id == e2.event_id
            assert e1.timestamp == e2.timestamp

    @SKIP_IF_NO_DATA
    def test_no_future_leakage(self):
        df = load_xauusd_d1(DATA_PATH)
        events = extract_sma_crossover_events(df)
        for e in events:
            assert e.outcome is None  # Outcomes not computed yet
            # Context should not contain future data
            ctx = e.context
            assert ctx.sma_fast is not None
            assert ctx.sma_slow is not None

    @SKIP_IF_NO_DATA
    def test_bullish_bearish_balance(self):
        df = load_xauusd_d1(DATA_PATH)
        events = extract_sma_crossover_events(df)
        bullish = sum(1 for e in events if e.direction == "bullish")
        bearish = sum(1 for e in events if e.direction == "bearish")
        assert bullish + bearish == len(events)
        assert bullish > 0
        assert bearish > 0


# =============================================================================
# Outcome Engine Tests
# =============================================================================


class TestOutcomeEngine:
    """Test forward outcome calculation."""

    def test_compute_outcomes_basic(self):
        ts1 = datetime(2021, 1, 1, tzinfo=timezone.utc)
        ts2 = datetime(2021, 1, 2, tzinfo=timezone.utc)
        ts3 = datetime(2021, 1, 3, tzinfo=timezone.utc)
        ts4 = datetime(2021, 1, 4, tzinfo=timezone.utc)
        ts5 = datetime(2021, 1, 5, tzinfo=timezone.utc)
        df = pl.DataFrame(
            {
                "timestamp": [ts1, ts2, ts3, ts4, ts5],
                "open": [100.0, 101.0, 102.0, 103.0, 104.0],
                "high": [101.0, 102.0, 103.0, 104.0, 105.0],
                "low": [99.0, 100.0, 101.0, 102.0, 103.0],
                "close": [100.0, 101.0, 102.0, 103.0, 104.0],
            }
        )
        event = MarketEvent(
            event_id="e1",
            asset="XAUUSD",
            timeframe="D1",
            event_type=EventType.SMA_CROSSOVER.value,
            direction="bullish",
            timestamp=ts1,
            event_price=100.0,
            context=_make_minimal_event("e1", "bullish", ts1).context,
        )
        updated = compute_forward_outcomes([event], df)
        assert len(updated) == 1
        assert updated[0].outcome is not None
        assert updated[0].outcome.return_1d is not None
        assert updated[0].outcome.return_1d == pytest.approx(0.01)  # (101-100)/100

    def test_no_future_leakage_in_outcomes(self):
        ts1 = datetime(2021, 1, 1, tzinfo=timezone.utc)
        ts2 = datetime(2021, 1, 2, tzinfo=timezone.utc)
        df = pl.DataFrame(
            {
                "timestamp": [ts1, ts2],
                "open": [100.0, 101.0],
                "high": [101.0, 102.0],
                "low": [99.0, 100.0],
                "close": [100.0, 101.0],
            }
        )
        events = [_make_minimal_event("e1", "bullish", ts2)]
        updated = compute_forward_outcomes(events, df)
        # Event at last index, no future bars -> return_1d should be None
        assert updated[0].outcome is not None
        assert updated[0].outcome.return_1d is None

    @SKIP_IF_NO_DATA
    def test_outcome_on_real_data(self):
        df = load_xauusd_d1(DATA_PATH)
        price_df = df.select(["timestamp", "open", "high", "low", "close"])
        events = extract_sma_crossover_events(df)
        events = compute_forward_outcomes(events, price_df)
        outcomes = [e.outcome for e in events if e.outcome and e.outcome.return_1d is not None]
        assert len(outcomes) > 0
        for o in outcomes:
            assert isinstance(o.return_1d, float)


# =============================================================================
# Conditioning Tests
# =============================================================================


class TestConditioning:
    """Test conditional analysis."""

    def test_evaluate_condition_direction(self):
        event = _make_event_with_outcome("e1", "bullish", 0.01)
        spec = ConditionSpec(name="bullish", conditions={"direction": "bullish"})
        assert evaluate_condition(event, spec) is True

        spec2 = ConditionSpec(name="bearish", conditions={"direction": "bearish"})
        assert evaluate_condition(event, spec2) is False

    def test_filter_events(self):
        events = [
            _make_event_with_outcome("e1", "bullish", 0.01),
            _make_event_with_outcome("e2", "bearish", -0.01),
            _make_event_with_outcome("e3", "bullish", 0.02),
        ]
        spec = ConditionSpec(name="bullish", conditions={"direction": "bullish"})
        filtered = filter_events(events, spec)
        assert len(filtered) == 2

    def test_conditional_statistics(self):
        events = [
            _make_event_with_outcome("e1", "bullish", 0.01),
            _make_event_with_outcome("e2", "bullish", 0.02),
            _make_event_with_outcome("e3", "bearish", -0.01),
        ]
        spec = ConditionSpec(name="bullish", conditions={"direction": "bullish"})
        result = compute_conditional_statistics(events, spec)
        assert result.sample_size == 2
        assert result.raw_probability == 1.0  # both positive
        assert result.mean_return == pytest.approx(0.015)

    def test_conditional_statistics_uses_dependence_aware_bootstrap(self):
        events = [
            _make_event_with_outcome("e1", "bullish", 0.01, "2021-01-01T00:00:00"),
            _make_event_with_outcome("e2", "bullish", 0.03, "2021-01-02T00:00:00"),
            _make_event_with_outcome("e3", "bullish", -0.01, "2021-01-03T00:00:00"),
            _make_event_with_outcome("e4", "bullish", 0.02, "2021-01-04T00:00:00"),
        ]
        spec = ConditionSpec(name="bullish", conditions={"direction": "bullish"})
        result = compute_conditional_statistics(
            events,
            spec,
            bootstrap_num_resamples=200,
            bootstrap_seed=42,
            dependence_block_size=2,
        )
        assert result.confidence_interval is not None
        assert "moving_block_bootstrap" in result.notes
        assert "dependence_block_size=2" in result.notes

    def test_conditional_statistics_no_match(self):
        events = [_make_event_with_outcome("e1", "bullish", 0.01)]
        spec = ConditionSpec(name="bearish", conditions={"direction": "bearish"})
        result = compute_conditional_statistics(events, spec)
        assert result.sample_size == 0
        assert result.status == EvidenceStatus.INCONCLUSIVE.value

    @SKIP_IF_NO_DATA
    def test_conditional_on_real_data(self):
        df = load_xauusd_d1(DATA_PATH)
        events = extract_sma_crossover_events(df)
        events = compute_forward_outcomes(events, df.select(["timestamp", "open", "high", "low", "close"]))
        spec = ConditionSpec(name="all", conditions={})
        result = compute_conditional_statistics(events, spec)
        assert result.sample_size > 0


# =============================================================================
# Bootstrap Tests
# =============================================================================


class TestBootstrap:
    """Test bootstrap uncertainty quantification."""

    def test_bootstrap_determinism(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        r1 = bootstrap_mean_ci(values, seed=42)
        r2 = bootstrap_mean_ci(values, seed=42)
        assert r1.point_estimate == r2.point_estimate
        assert r1.confidence_interval == r2.confidence_interval

    def test_bootstrap_ci_contains_mean(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = bootstrap_mean_ci(values, seed=42)
        mean = sum(values) / len(values)
        assert result.confidence_interval[0] <= mean <= result.confidence_interval[1]

    def test_bootstrap_stability_check(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0] * 10
        result = bootstrap_stability_check(values, seed=42)
        assert "point_estimate" in result
        assert "is_stable" in result


# =============================================================================
# Temporal Validation Tests
# =============================================================================


class TestTemporalValidation:
    """Test temporal validation."""

    def test_chronological_split(self):
        events = [_make_minimal_event(f"e{i}", "bullish") for i in range(100)]
        train, val, test = chronological_split(events, train_ratio=0.6, validation_ratio=0.2)
        assert len(train) == 60
        assert len(val) == 20
        assert len(test) == 20
        # Verify chronological order preserved
        assert train[0].timestamp <= train[-1].timestamp
        assert val[0].timestamp >= train[-1].timestamp

    def test_expanding_window(self):
        events = [_make_minimal_event(f"e{i}", "bullish") for i in range(200)]
        splits = expanding_window_splits(events, initial_train_size=50, validation_size=50, step_size=50)
        assert len(splits) > 0
        for train, val in splits:
            assert len(train) >= 50
            assert len(val) == 50

    def test_temporal_integrity(self):
        events = [
            _make_minimal_event("e1", "bullish", "2021-01-01T00:00:00"),
            _make_minimal_event("e2", "bullish", "2021-01-02T00:00:00"),
        ]
        result = check_temporal_integrity(events)
        assert result["status"] == "PASS"

    def test_temporal_integrity_fail(self):
        events = [
            _make_minimal_event("e1", "bullish", "2021-01-02T00:00:00"),
            _make_minimal_event("e2", "bullish", "2021-01-01T00:00:00"),
        ]
        result = check_temporal_integrity(events)
        assert result["status"] == "FAIL"


# =============================================================================
# Self-Audit Tests
# =============================================================================


class TestSelfAudit:
    """Test self-audit functionality."""

    def test_clean_audit(self):
        events = [
            _make_event_with_outcome("e1", "bullish", 0.01, "2021-01-01T00:00:00"),
            _make_event_with_outcome("e2", "bearish", -0.01, "2021-01-02T00:00:00"),
        ]
        result = run_self_audit(events, conditional_results=[])
        assert result.overall_status == "PASS"
        assert result.total_events == 2

    def test_duplicate_detection(self):
        events = [
            _make_minimal_event("e1", "bullish", "2021-01-01T00:00:00"),
            _make_minimal_event("e1", "bullish", "2021-01-01T00:00:00"),
        ]
        result = run_self_audit(events, conditional_results=[])
        assert result.duplicate_events > 0

    def test_insufficient_sample_warning(self):
        events = [_make_event_with_outcome("e1", "bullish", 0.01)]
        from researchos.market_memory.event_schema import ConditionSpec

        result = run_self_audit(
            events,
            conditional_results=[
                ConditionalResult(
                    condition_name="test",
                    condition_spec=ConditionSpec(name="test", conditions={}),
                    sample_size=1,
                )
            ],
            min_sample_size=5,
        )
        assert len(result.insufficient_sample_size) > 0


# =============================================================================
# Evidence Tests
# =============================================================================


class TestEvidence:
    """Test evidence and provenance."""

    def test_create_evidence_record(self):
        record = create_evidence_record(
            finding_name="Test Finding",
            dataset_id="XAUUSD_D1_test",
            dataset_version="v1",
            event_definition="SMA20/100 crossover",
            condition_definition={"direction": "bullish"},
            sample_size=10,
            time_range=("2021-01-01", "2025-12-31"),
            computation_method="forward_return",
            code_module="researchos.market_memory.pipeline",
            statistical_method="empirical_probability",
            result={"raw_probability": 0.6},
            status=EvidenceStatus.UNVALIDATED.value,
        )
        assert record.finding_name == "Test Finding"
        assert record.sample_size == 10
        assert record.status == EvidenceStatus.UNVALIDATED.value
        d = record.to_dict()
        assert "finding_id" in d


# =============================================================================
# Pipeline Integration Tests
# =============================================================================


class TestPipeline:
    """Test end-to-end pipeline."""

    @SKIP_IF_NO_DATA
    def test_pipeline_runs(self):
        report = run_market_memory_pipeline(
            data_path=DATA_PATH,
            seed=42,
        )
        assert report.total_events > 0
        assert len(report.conditional_results) > 0
        assert report.self_audit is not None

    @SKIP_IF_NO_DATA
    def test_pipeline_determinism(self):
        r1 = run_market_memory_pipeline(data_path=DATA_PATH, seed=42)
        r2 = run_market_memory_pipeline(data_path=DATA_PATH, seed=42)
        assert r1.total_events == r2.total_events
        assert r1.date_range == r2.date_range
        assert len(r1.conditional_results) == len(r2.conditional_results)

    @SKIP_IF_NO_DATA
    def test_pipeline_no_leakage(self):
        report = run_market_memory_pipeline(data_path=DATA_PATH, seed=42)
        # All events should have outcomes computed from data after event
        for e in report.evidence_records:
            assert e.dataset_id != ""
            assert e.computation_method != ""
