"""Additive adapter for timestamped, pre-assessed XAUUSD macro evidence.

This adapter does not fetch macro data or alter MacroAnalysisEngine scoring.
A provider must supply explicit gold-impact direction, score, confidence,
source references, and a per-observation freshness contract.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from researchos.macro.engine import ALL_DRIVERS
from researchos.orchestration.xauusd_research import (
    DECISION_TIMEFRAME,
    EngineResult,
    EngineStatus,
    EvidenceRecord,
    XAUUSDResearchRequest,
)

MACRO_ADAPTER_VERSION = "XAUUSD_MACRO_EVIDENCE_ADAPTER_V1"


@dataclass(frozen=True)
class MacroDriverObservation:
    """One already-assessed macro driver with explicit provenance and freshness."""

    driver_name: str
    score: float
    confidence: float
    gold_impact_direction: int
    as_of: datetime
    source_refs: tuple[str, ...]
    max_age_seconds: int

    def __post_init__(self) -> None:
        if not isinstance(self.driver_name, str) or self.driver_name not in ALL_DRIVERS:
            raise ValueError("UNSUPPORTED_MACRO_DRIVER")
        for name, value in (("score", self.score), ("confidence", self.confidence)):
            if isinstance(value, bool):
                raise ValueError(f"INVALID_MACRO_{name.upper()}")
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"INVALID_MACRO_{name.upper()}") from exc
            if not math.isfinite(number):
                raise ValueError(f"INVALID_MACRO_{name.upper()}")
        if not 0.0 <= float(self.score) <= 100.0:
            raise ValueError("INVALID_MACRO_SCORE")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("INVALID_MACRO_CONFIDENCE")
        if isinstance(self.gold_impact_direction, bool) or self.gold_impact_direction not in (-1, 0, 1):
            raise ValueError("INVALID_MACRO_DIRECTION")
        if not isinstance(self.as_of, datetime) or self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("MACRO_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        if (
            not isinstance(self.source_refs, tuple)
            or not self.source_refs
            or any(not isinstance(ref, str) or not ref.strip() for ref in self.source_refs)
        ):
            raise ValueError("MACRO_SOURCE_PROVENANCE_REQUIRED")
        if isinstance(self.max_age_seconds, bool) or not isinstance(self.max_age_seconds, int) or self.max_age_seconds <= 0:
            raise ValueError("MACRO_MAX_AGE_MUST_BE_POSITIVE_INTEGER")


@dataclass(frozen=True)
class XAUUSDMacroSnapshot:
    """Immutable macro-driver collection produced by a configured data provider."""

    provider_id: str
    observations: tuple[MacroDriverObservation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, str) or not self.provider_id.strip():
            raise ValueError("MACRO_PROVIDER_ID_REQUIRED")
        if not isinstance(self.observations, tuple) or not self.observations:
            raise ValueError("MACRO_OBSERVATIONS_REQUIRED")
        if any(not isinstance(item, MacroDriverObservation) for item in self.observations):
            raise ValueError("INVALID_MACRO_OBSERVATION_TYPE")
        names = [observation.driver_name for observation in self.observations]
        if len(names) != len(set(names)):
            raise ValueError("DUPLICATE_MACRO_DRIVER")


class XAUUSDMacroEvidenceAdapter:
    """Translate macro observations into the shared evidence contract.

    All ten existing macro driver identifiers are required. The adapter
    refuses future or stale observations and does not infer direction from a
    score; direction must be explicitly supplied by the macro assessment.
    """

    engine_name = "macro"
    engine_version = MACRO_ADAPTER_VERSION

    def __call__(
        self,
        request: XAUUSDResearchRequest,
        macro_snapshot: object,
    ) -> EngineResult:
        if not isinstance(macro_snapshot, XAUUSDMacroSnapshot):
            return EngineResult(
                engine_name=self.engine_name,
                status=EngineStatus.NOT_CONFIGURED,
                reason_codes=("MACRO_PROVIDER_NOT_CONFIGURED",),
                engine_version=self.engine_version,
            )

        by_name = {item.driver_name: item for item in macro_snapshot.observations}
        missing = tuple(name for name in ALL_DRIVERS if name not in by_name)
        if missing:
            return EngineResult(
                engine_name=self.engine_name,
                status=EngineStatus.INSUFFICIENT,
                reason_codes=tuple(f"MACRO_DRIVER_MISSING:{name}" for name in missing),
                engine_version=self.engine_version,
            )

        records: list[EvidenceRecord] = []
        for driver_name in ALL_DRIVERS:
            observation = by_name[driver_name]
            age_seconds = (request.decision_time - observation.as_of).total_seconds()
            if age_seconds < 0:
                return EngineResult(
                    engine_name=self.engine_name,
                    status=EngineStatus.FAILED,
                    reason_codes=(f"FUTURE_MACRO_OBSERVATION:{driver_name}",),
                    engine_version=self.engine_version,
                )
            if age_seconds > observation.max_age_seconds:
                return EngineResult(
                    engine_name=self.engine_name,
                    status=EngineStatus.INSUFFICIENT,
                    reason_codes=(f"STALE_MACRO_OBSERVATION:{driver_name}",),
                    engine_version=self.engine_version,
                )
            records.append(
                EvidenceRecord(
                    evidence_id=f"{request.run_id}:macro:{driver_name}",
                    engine_name=self.engine_name,
                    instrument=request.instrument,
                    as_of=observation.as_of,
                    timeframe=DECISION_TIMEFRAME,
                    feature_name=f"macro_{driver_name.lower()}_score",
                    value=float(observation.score),
                    direction=observation.gold_impact_direction,
                    strength=float(observation.confidence),
                    quality=float(observation.confidence),
                    dependency_group=f"macro:{driver_name}",
                    source_refs=(macro_snapshot.provider_id, *observation.source_refs),
                )
            )

        return EngineResult(
            engine_name=self.engine_name,
            status=EngineStatus.OK,
            evidence=tuple(records),
            engine_version=self.engine_version,
        )


__all__ = [
    "MacroDriverObservation",
    "XAUUSDMacroSnapshot",
    "XAUUSDMacroEvidenceAdapter",
]
