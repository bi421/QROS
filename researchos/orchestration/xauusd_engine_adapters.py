"""Concrete adapters from existing XAUUSD technical and quant engines.

This module is additive: it calls existing calculations and translates their
outputs into the canonical evidence contract. Heuristic strengths are feature
scales, not calibrated probabilities. No order/execution code is involved.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Sequence

from researchos.orchestration.xauusd_research import (
    CONTEXT_TIMEFRAMES,
    DECISION_TIMEFRAME,
    EngineResult,
    EngineStatus,
    EvidenceRecord,
    XAUUSDResearchRequest,
)
from researchos.quant_engine.technical import (
    Bars,
    IndicatorSpec,
    TechnicalAnalysisEngine,
    get_technical_engine,
)
from researchos.quant_math.engine import QuantMathEngine

ALL_TIMEFRAMES = (DECISION_TIMEFRAME, *CONTEXT_TIMEFRAMES)
MAX_BARS_PER_TIMEFRAME = 512


@dataclass(frozen=True)
class XAUUSDMarketSnapshot:
    """Bounded, timestamp-aligned OHLCV windows supplied by a data adapter.

    Timestamps represent each bar's close time and must be timezone-aware,
    strictly increasing, and aligned one-to-one with each Bars series.
    """

    bars_by_timeframe: Mapping[str, Bars]
    bar_close_times_by_timeframe: Mapping[str, Sequence[datetime]]
    dataset_version: str
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        expected = set(ALL_TIMEFRAMES)
        if set(self.bars_by_timeframe) != expected:
            raise ValueError("snapshot must provide exactly M15, M30, H1, H4, and D1 bars")
        if set(self.bar_close_times_by_timeframe) != expected:
            raise ValueError("snapshot timestamps must cover exactly all supported timeframes")
        if not self.dataset_version.strip():
            raise ValueError("dataset_version is required")
        for timeframe in ALL_TIMEFRAMES:
            bars = self.bars_by_timeframe[timeframe]
            timestamps = self.bar_close_times_by_timeframe[timeframe]
            bars.validate()
            if bars.length == 0 or len(timestamps) != bars.length:
                raise ValueError(
                    f"{timeframe} bars and close timestamps must have equal non-zero length"
                )
            previous: datetime | None = None
            for timestamp in timestamps:
                if (
                    not isinstance(timestamp, datetime)
                    or timestamp.tzinfo is None
                    or timestamp.utcoffset() is None
                ):
                    raise ValueError(f"{timeframe} close timestamps must be timezone-aware")
                if previous is not None and timestamp <= previous:
                    raise ValueError(f"{timeframe} close timestamps must be strictly increasing")
                previous = timestamp


def _window_at(
    snapshot: XAUUSDMarketSnapshot,
    timeframe: str,
    decision_time: datetime,
) -> tuple[Bars, datetime]:
    timestamps = snapshot.bar_close_times_by_timeframe[timeframe]
    end = bisect_right(timestamps, decision_time)
    if end == 0:
        raise ValueError(f"NO_CLOSED_BARS_AS_OF_DECISION:{timeframe}")
    start = max(0, end - MAX_BARS_PER_TIMEFRAME)
    original = snapshot.bars_by_timeframe[timeframe]
    window = Bars(
        open=list(original.open[start:end]),
        high=list(original.high[start:end]),
        low=list(original.low[start:end]),
        close=list(original.close[start:end]),
        volume=list(original.volume[start:end]),
    )
    return window, timestamps[end - 1]


def _last_value(values: Sequence[float | None], name: str) -> float:
    if not values or values[-1] is None:
        raise ValueError(f"INDICATOR_VALUE_UNAVAILABLE:{name}")
    value = float(values[-1])
    if not math.isfinite(value):
        raise ValueError(f"INDICATOR_VALUE_NONFINITE:{name}")
    return value


def _direction(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _bounded(value: float) -> float:
    return min(1.0, max(0.0, value))


class XAUUSDTechnicalEvidenceAdapter:
    """Run existing indicators on every closed timeframe and emit typed evidence."""

    engine_name = "technical"
    engine_version = "XAUUSD_TECHNICAL_ADAPTER_V1"

    def __init__(self, engine: TechnicalAnalysisEngine | None = None) -> None:
        self.engine = engine or get_technical_engine()

    def __call__(
        self,
        request: XAUUSDResearchRequest,
        market_snapshot: object,
    ) -> EngineResult:
        if not isinstance(market_snapshot, XAUUSDMarketSnapshot):
            raise TypeError("technical adapter requires XAUUSDMarketSnapshot")
        if market_snapshot.dataset_version != request.dataset_version:
            raise ValueError("DATASET_VERSION_MISMATCH")
        records: list[EvidenceRecord] = []
        for timeframe in ALL_TIMEFRAMES:
            bars, as_of = _window_at(market_snapshot, timeframe, request.decision_time)
            if bars.length < 60:
                raise ValueError(f"INSUFFICIENT_TECHNICAL_HISTORY:{timeframe}")
            ema_fast = self.engine.compute(bars, IndicatorSpec("EMA", {"period": 20}))
            ema_slow = self.engine.compute(bars, IndicatorSpec("EMA", {"period": 50}))
            rsi = self.engine.compute(bars, IndicatorSpec("RSI", {"period": 14}))
            atr = self.engine.compute(bars, IndicatorSpec("ATR", {"period": 14}))
            macd = self.engine.compute(
                bars, IndicatorSpec("MACD", {"fast": 12, "slow": 26, "signal": 9})
            )
            supertrend = self.engine.compute(
                bars, IndicatorSpec("SuperTrend", {"period": 10, "multiplier": 3.0})
            )

            atr_value = _last_value(atr.values, "ATR_14")
            if atr_value <= 0:
                raise ValueError(f"INVALID_ATR:{timeframe}")
            ema_difference = _last_value(ema_fast.values, "EMA_20") - _last_value(
                ema_slow.values, "EMA_50"
            )
            rsi_value = _last_value(rsi.values, "RSI_14")
            macd_histogram = _last_value(macd.aux.get("histogram", ()), "MACD_HISTOGRAM")
            trend_series = supertrend.aux.get("trend", ())
            trend_value = _last_value(trend_series, "SUPERTREND_DIRECTION")
            if trend_value not in (-1.0, 1.0):
                raise ValueError(f"INVALID_SUPERTREND_DIRECTION:{timeframe}")

            features = (
                (
                    "ema_alignment",
                    ema_difference,
                    _direction(ema_difference),
                    _bounded(abs(ema_difference) / atr_value),
                ),
                (
                    "rsi_centered",
                    rsi_value,
                    _direction(rsi_value - 50.0),
                    _bounded(abs(rsi_value - 50.0) / 25.0),
                ),
                (
                    "macd_histogram",
                    macd_histogram,
                    _direction(macd_histogram),
                    _bounded(abs(macd_histogram) / atr_value),
                ),
                (
                    "supertrend_direction",
                    trend_value,
                    int(trend_value),
                    1.0,
                ),
                ("atr_14", atr_value, 0, 0.0),
            )
            for feature, value, direction, strength in features:
                records.append(
                    EvidenceRecord(
                        evidence_id=f"{request.run_id}:technical:{timeframe}:{feature}",
                        engine_name=self.engine_name,
                        instrument=request.instrument,
                        as_of=as_of,
                        timeframe=timeframe,
                        feature_name=feature,
                        value=value,
                        direction=direction,
                        strength=strength,
                        quality=1.0,
                        dependency_group="price-derived",
                        source_refs=tuple(market_snapshot.source_refs)
                        + (market_snapshot.dataset_version,),
                    )
                )
        return EngineResult(
            engine_name=self.engine_name,
            status=EngineStatus.OK,
            evidence=tuple(records),
            engine_version=self.engine_version,
        )


class XAUUSDQuantMathEvidenceAdapter:
    """Run existing deterministic geometry/statistics over the closed M15 window."""

    engine_name = "quant_math"
    engine_version = "XAUUSD_QUANT_MATH_ADAPTER_V1"

    def __init__(self, engine: QuantMathEngine | None = None) -> None:
        self.engine = engine or QuantMathEngine()

    def __call__(
        self,
        request: XAUUSDResearchRequest,
        market_snapshot: object,
    ) -> EngineResult:
        if not isinstance(market_snapshot, XAUUSDMarketSnapshot):
            raise TypeError("quant-math adapter requires XAUUSDMarketSnapshot")
        if market_snapshot.dataset_version != request.dataset_version:
            raise ValueError("DATASET_VERSION_MISMATCH")
        bars, as_of = _window_at(market_snapshot, DECISION_TIMEFRAME, request.decision_time)
        if bars.length < 60:
            return EngineResult(
                engine_name=self.engine_name,
                status=EngineStatus.INSUFFICIENT,
                reason_codes=("INSUFFICIENT_QUANT_HISTORY:M15",),
                engine_version=self.engine_version,
            )
        result = self.engine.evaluate(prices=bars.close)
        features: list[tuple[str, float, int, float]] = [
            (
                "geometry_slope",
                float(result.geometry.slope),
                _direction(float(result.geometry.slope)),
                _bounded(abs(float(result.geometry.trend_r2))),
            ),
            (
                "z_score_last",
                float(result.statistics.z_score_last),
                _direction(float(result.statistics.z_score_last)),
                _bounded(abs(float(result.statistics.z_score_last)) / 3.0),
            ),
        ]
        if result.statistics.regression_slope is not None:
            regression_slope = float(result.statistics.regression_slope)
            regression_r2 = float(result.statistics.regression_r2 or 0.0)
            features.append(
                (
                    "regression_slope",
                    regression_slope,
                    _direction(regression_slope),
                    _bounded(abs(regression_r2)),
                )
            )
        records = tuple(
            EvidenceRecord(
                evidence_id=f"{request.run_id}:quant-math:{result.result_hash}:{feature}",
                engine_name=self.engine_name,
                instrument=request.instrument,
                as_of=as_of,
                timeframe=DECISION_TIMEFRAME,
                feature_name=feature,
                value=value,
                direction=direction,
                strength=strength,
                quality=1.0,
                dependency_group="price-derived",
                source_refs=tuple(market_snapshot.source_refs)
                + (market_snapshot.dataset_version, result.result_hash),
            )
            for feature, value, direction, strength in features
            if math.isfinite(value) and math.isfinite(strength)
        )
        if not records:
            return EngineResult(
                engine_name=self.engine_name,
                status=EngineStatus.INSUFFICIENT,
                reason_codes=("NO_VALID_QUANT_EVIDENCE",),
                engine_version=self.engine_version,
            )
        return EngineResult(
            engine_name=self.engine_name,
            status=EngineStatus.OK,
            evidence=records,
            engine_version=result.calculation_version,
        )


__all__ = [
    "ALL_TIMEFRAMES",
    "MAX_BARS_PER_TIMEFRAME",
    "XAUUSDMarketSnapshot",
    "XAUUSDQuantMathEvidenceAdapter",
    "XAUUSDTechnicalEvidenceAdapter",
]
