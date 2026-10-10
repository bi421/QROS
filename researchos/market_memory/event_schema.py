"""
Market Memory V1 — Event schema and outcome contracts.

Defines the deterministic data structures for:
  - MarketEvent: discrete market events (e.g., SMA crossover)
  - EventContext: conditioning variables at event time
  - EventOutcome: forward return outcomes at multiple horizons
  - ConditionSpec: specification of a conditional analysis query
  - ConditionalResult: result of a conditional analysis
  - BootstrapResult: bootstrap uncertainty quantification
  - ValidationResult: temporal validation results
  - EvidenceRecord: provenance and evidence tracking
  - SelfAuditResult: self-audit results
  - MarketMemoryReport: consolidated market memory report

All objects are deterministic, serializable, and hashable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# =============================================================================
# Enums
# =============================================================================


class EventType(str, Enum):
    SMA_CROSSOVER = "sma_crossover"
    # Future: BREAKOUT, REVERSAL, REGIME_CHANGE, etc.


class CrossoverDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class MarketRegime(str, Enum):
    TRENDING_UP = "Trending_Up"
    TRENDING_DOWN = "Trending_Down"
    RANGING = "Ranging"
    VOLATILE = "Volatile"
    QUIET = "Quiet"
    UNKNOWN = "Unknown"


class Session(str, Enum):
    ASIAN = "Asian"
    EUROPEAN = "European"
    US = "US"
    OVERLAP = "Overlap"
    UNKNOWN = "Unknown"


class EvidenceStatus(str, Enum):
    EXPLORATORY = "EXPLORATORY"
    UNVALIDATED = "UNVALIDATED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


# =============================================================================
# Event and Outcome Models
# =============================================================================


@dataclass(frozen=True)
class EventOutcome:
    """
    Forward return outcomes for a market event at multiple horizons.

    All returns are computed from the event timestamp forward.
    Fields that cannot be computed from the available data are marked
    as FIELD_UNAVAILABLE.
    """

    event_id: str
    asset: str
    timeframe: str
    event_timestamp: datetime

    # Forward returns (absolute and percentage)
    return_5m: str = "FIELD_UNAVAILABLE"
    return_15m: str = "FIELD_UNAVAILABLE"
    return_30m: str = "FIELD_UNAVAILABLE"
    return_1h: str = "FIELD_UNAVAILABLE"
    return_4h: str = "FIELD_UNAVAILABLE"
    return_1d: float | None = None
    return_2d: float | None = None
    return_3d: float | None = None
    return_5d: float | None = None
    return_10d: float | None = None
    return_20d: float | None = None

    # Direction of movement
    direction_5m: str | None = None
    direction_15m: str | None = None
    direction_30m: str | None = None
    direction_1h: str | None = None
    direction_4h: str | None = None
    direction_1d: str | None = None
    direction_2d: str | None = None
    direction_3d: str | None = None
    direction_5d: str | None = None
    direction_10d: str | None = None
    direction_20d: str | None = None

    # Maximum favorable/adverse excursion
    mfe_1d: float | None = None
    mae_1d: float | None = None
    mfe_5d: float | None = None
    mae_5d: float | None = None
    mfe_20d: float | None = None
    mae_20d: float | None = None

    # Hit/miss for thresholds
    hit_threshold_1d: bool | None = None
    hit_threshold_5d: bool | None = None
    hit_threshold_20d: bool | None = None

    # Metadata
    outcome_calculation_method: str = "forward_return_from_event_timestamp"
    data_availability: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "event_timestamp": self.event_timestamp.isoformat(),
            "return_5m": self.return_5m,
            "return_15m": self.return_15m,
            "return_30m": self.return_30m,
            "return_1h": self.return_1h,
            "return_4h": self.return_4h,
            "return_1d": self.return_1d,
            "direction_5m": self.direction_5m,
            "direction_15m": self.direction_15m,
            "direction_30m": self.direction_30m,
            "direction_1h": self.direction_1h,
            "direction_4h": self.direction_4h,
            "direction_1d": self.direction_1d,
            "mfe_1d": self.mfe_1d,
            "mae_1d": self.mae_1d,
            "hit_threshold_1d": self.hit_threshold_1d,
            "outcome_calculation_method": self.outcome_calculation_method,
            "data_availability": self.data_availability,
        }


@dataclass(frozen=True)
class EventContext:
    """
    Conditioning variables at the time of a market event.

    Only includes variables that can be computed from the validated dataset.
    Unavailable variables are explicitly marked as FIELD_UNAVAILABLE.
    """

    event_id: str
    asset: str
    timeframe: str
    timestamp: datetime

    # Price context
    event_price: float = 0.0
    open_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    close_price: float = 0.0

    # Volume context
    tick_volume: int = 0

    # Technical indicators (computed from price data)
    sma_fast: float = 0.0
    sma_slow: float = 0.0
    atr: float = 0.0
    rsi: float = 0.0
    macd_line: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0

    # Market context
    market_regime: str = MarketRegime.UNKNOWN.value
    volatility_state: str = "Unknown"

    # Time context
    day_of_week: int = 0
    session: str = Session.UNKNOWN.value

    # Preceding returns
    preceding_return_1d: float | None = None
    preceding_return_3d: float | None = None
    preceding_return_5d: float | None = None

    # Unavailable fields (explicitly recorded)
    spread: str = "FIELD_UNAVAILABLE"
    dxy: str = "FIELD_UNAVAILABLE"
    us10y: str = "FIELD_UNAVAILABLE"
    vix: str = "FIELD_UNAVAILABLE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat(),
            "event_price": self.event_price,
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "close_price": self.close_price,
            "tick_volume": self.tick_volume,
            "sma_fast": self.sma_fast,
            "sma_slow": self.sma_slow,
            "atr": self.atr,
            "rsi": self.rsi,
            "macd_line": self.macd_line,
            "macd_signal": self.macd_signal,
            "macd_histogram": self.macd_histogram,
            "market_regime": self.market_regime,
            "volatility_state": self.volatility_state,
            "day_of_week": self.day_of_week,
            "session": self.session,
            "preceding_return_1d": self.preceding_return_1d,
            "preceding_return_3d": self.preceding_return_3d,
            "preceding_return_5d": self.preceding_return_5d,
            "spread": self.spread,
            "dxy": self.dxy,
            "us10y": self.us10y,
            "vix": self.vix,
        }


@dataclass(frozen=True)
class MarketEvent:
    """
    A discrete market event (e.g., SMA crossover).

    Combines event identification, context, and outcome into a single
    immutable, hashable record.
    """

    event_id: str
    asset: str
    timeframe: str
    event_type: str
    direction: str
    timestamp: datetime
    event_price: float

    # Context at event time
    context: EventContext

    # Forward outcomes
    outcome: EventOutcome | None = None

    # Provenance
    dataset_source: str = ""
    computation_method: str = ""
    seed: int = 42

    def __post_init__(self):
        if self.event_id == "":
            raise ValueError("event_id cannot be empty")
        if self.asset == "":
            raise ValueError("asset cannot be empty")
        if self.timeframe == "":
            raise ValueError("timeframe cannot be empty")
        if self.event_type == "":
            raise ValueError("event_type cannot be empty")
        if self.direction == "":
            raise ValueError("direction cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "event_type": self.event_type,
            "direction": self.direction,
            "timestamp": self.timestamp.isoformat(),
            "event_price": self.event_price,
            "context": self.context.to_dict() if self.context else None,
            "outcome": self.outcome.to_dict() if self.outcome else None,
            "dataset_source": self.dataset_source,
            "computation_method": self.computation_method,
            "seed": self.seed,
        }


# =============================================================================
# Conditional Analysis
# =============================================================================


@dataclass(frozen=True)
class ConditionSpec:
    """
    Specification of a conditional analysis query.

    Example:
        ConditionSpec(
            name="bullish_crossover_low_vol",
            conditions={
                "direction": "bullish",
                "volatility_state": "Low",
            },
        )
    """

    name: str
    conditions: dict[str, Any]
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "conditions": dict(sorted(self.conditions.items())),
            "description": self.description,
        }


@dataclass(frozen=True)
class ConditionalResult:
    """
    Result of a conditional analysis on a set of events.
    """

    condition_name: str
    condition_spec: ConditionSpec
    sample_size: int = 0
    raw_probability: float = 0.0
    # Fraction of finite outcomes moving in the event's declared direction.
    # None means at least one event direction was not recognized.
    directional_probability: float | None = None
    probability_definition: str = "P(return > 0); raw positive-return frequency"
    mean_return: float = 0.0
    std_return: float = 0.0
    confidence_interval: tuple[float, float] | None = None
    bootstrap_seed: int = 42
    bootstrap_num_resamples: int = 1000
    status: str = EvidenceStatus.EXPLORATORY.value
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition_name": self.condition_name,
            "condition_spec": self.condition_spec.to_dict(),
            "sample_size": self.sample_size,
            "raw_probability": self.raw_probability,
            "directional_probability": self.directional_probability,
            "probability_definition": self.probability_definition,
            "mean_return": self.mean_return,
            "std_return": self.std_return,
            "confidence_interval": list(self.confidence_interval) if self.confidence_interval else None,
            "bootstrap_seed": self.bootstrap_seed,
            "bootstrap_num_resamples": self.bootstrap_num_resamples,
            "status": self.status,
            "notes": self.notes,
        }


# =============================================================================
# Bootstrap and Validation
# =============================================================================


@dataclass(frozen=True)
class BootstrapResult:
    """
    Bootstrap uncertainty quantification for a statistic.
    """

    point_estimate: float
    bootstrap_mean: float
    bootstrap_std: float
    confidence_interval: tuple[float, float]
    confidence_level: float = 0.95
    num_resamples: int = 1000
    seed: int = 42
    method: str = "percentile_bootstrap"

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_estimate": self.point_estimate,
            "bootstrap_mean": self.bootstrap_mean,
            "bootstrap_std": self.bootstrap_std,
            "confidence_interval": list(self.confidence_interval),
            "confidence_level": self.confidence_level,
            "num_resamples": self.num_resamples,
            "seed": self.seed,
            "method": self.method,
        }


@dataclass(frozen=True)
class ValidationResult:
    """
    Temporal validation result for a condition or model.
    """

    condition_name: str
    train_period: tuple[str, str]
    validation_period: tuple[str, str]
    test_period: tuple[str, str]
    train_events: int = 0
    validation_events: int = 0
    test_events: int = 0
    train_statistic: float = 0.0
    validation_statistic: float = 0.0
    test_statistic: float = 0.0
    is_stable: bool = False
    validation_method: str = "walk_forward"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition_name": self.condition_name,
            "train_period": list(self.train_period),
            "validation_period": list(self.validation_period),
            "test_period": list(self.test_period),
            "train_events": self.train_events,
            "validation_events": self.validation_events,
            "test_events": self.test_events,
            "train_statistic": self.train_statistic,
            "validation_statistic": self.validation_statistic,
            "test_statistic": self.test_statistic,
            "is_stable": self.is_stable,
            "validation_method": self.validation_method,
            "notes": self.notes,
        }


# =============================================================================
# Evidence and Provenance
# =============================================================================


@dataclass(frozen=True)
class EvidenceRecord:
    """
    Provenance and evidence tracking for a research finding.
    """

    finding_id: str
    finding_name: str
    dataset_id: str
    dataset_version: str
    event_definition: str
    condition_definition: str
    sample_size: int
    time_range: tuple[str, str]
    computation_method: str
    code_module: str
    statistical_method: str
    random_seed: int | None = None
    validation_method: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    uncertainty: dict[str, Any] = field(default_factory=dict)
    status: str = EvidenceStatus.EXPLORATORY.value
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "finding_name": self.finding_name,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "event_definition": self.event_definition,
            "condition_definition": self.condition_definition,
            "sample_size": self.sample_size,
            "time_range": list(self.time_range),
            "computation_method": self.computation_method,
            "code_module": self.code_module,
            "statistical_method": self.statistical_method,
            "random_seed": self.random_seed,
            "validation_method": self.validation_method,
            "result": self.result,
            "uncertainty": self.uncertainty,
            "status": self.status,
            "created_at": self.created_at,
        }


# =============================================================================
# Self-Audit
# =============================================================================


@dataclass(frozen=True)
class SelfAuditResult:
    """
    Result of a research self-audit.
    """

    audit_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_events: int = 0
    duplicate_events: int = 0
    timestamp_violations: int = 0
    future_leakage_detected: bool = False
    overlapping_windows: int = 0
    insufficient_sample_size: list[str] = field(default_factory=list)
    condition_explosion_risk: bool = False
    multiple_testing_risk: bool = False
    train_test_contamination: bool = False
    unstable_results: list[str] = field(default_factory=list)
    missing_provenance: list[str] = field(default_factory=list)
    invalid_probability_claims: list[str] = field(default_factory=list)
    reproducibility_failures: list[str] = field(default_factory=list)
    overall_status: str = "PASS"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_timestamp": self.audit_timestamp,
            "total_events": self.total_events,
            "duplicate_events": self.duplicate_events,
            "timestamp_violations": self.timestamp_violations,
            "future_leakage_detected": self.future_leakage_detected,
            "overlapping_windows": self.overlapping_windows,
            "insufficient_sample_size": self.insufficient_sample_size,
            "condition_explosion_risk": self.condition_explosion_risk,
            "multiple_testing_risk": self.multiple_testing_risk,
            "train_test_contamination": self.train_test_contamination,
            "unstable_results": self.unstable_results,
            "missing_provenance": self.missing_provenance,
            "invalid_probability_claims": self.invalid_probability_claims,
            "reproducibility_failures": self.reproducibility_failures,
            "overall_status": self.overall_status,
            "notes": self.notes,
        }


# =============================================================================
# Report
# =============================================================================


@dataclass(frozen=True)
class MarketMemoryReport:
    """
    Consolidated market memory research report.
    """

    report_id: str
    asset: str
    timeframe: str
    event_type: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Event summary
    total_events: int = 0
    date_range: tuple[str, str] = ("", "")

    # Outcome summary
    outcomes: dict[str, Any] = field(default_factory=dict)

    # Conditional analysis
    conditional_results: list[ConditionalResult] = field(default_factory=list)

    # Validation
    validation_results: list[ValidationResult] = field(default_factory=list)

    # Evidence
    evidence_records: list[EvidenceRecord] = field(default_factory=list)

    # Self-audit
    self_audit: SelfAuditResult | None = None

    # Status
    overall_status: str = EvidenceStatus.EXPLORATORY.value
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "event_type": self.event_type,
            "generated_at": self.generated_at,
            "total_events": self.total_events,
            "date_range": list(self.date_range),
            "outcomes": self.outcomes,
            "conditional_results": [cr.to_dict() for cr in self.conditional_results],
            "validation_results": [vr.to_dict() for vr in self.validation_results],
            "evidence_records": [er.to_dict() for er in self.evidence_records],
            "self_audit": self.self_audit.to_dict() if self.self_audit else None,
            "overall_status": self.overall_status,
            "notes": self.notes,
        }
