"""Additive XAUUSD multi-timeframe research orchestration contracts.

This module deliberately does not modify or replace existing research engines.
It coordinates injected adapters and validates their evidence at a single
decision timestamp. It does not calculate trading probabilities or execute
orders.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


DECISION_TIMEFRAME = "M15"
CONTEXT_TIMEFRAMES = ("M30", "H1", "H4", "D1")
SUPPORTED_TIMEFRAMES = frozenset((DECISION_TIMEFRAME, *CONTEXT_TIMEFRAMES))


class ResearchStatus(str, Enum):
    EVIDENCE_COLLECTED = "EVIDENCE_COLLECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class EngineStatus(str, Enum):
    OK = "OK"
    INSUFFICIENT = "INSUFFICIENT"
    FAILED = "FAILED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class OutcomeLabel(str, Enum):
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    TIMEOUT = "TIMEOUT"


class XAUUSDResearchError(ValueError):
    """Raised when a request or evidence record violates its contract."""


def _require_aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise XAUUSDResearchError(f"{name} must be a timezone-aware datetime")


@dataclass(frozen=True)
class OutcomeSpec:
    """Versioned label parameters; values are research defaults, not a strategy."""

    method: str = "ATR_TRIPLE_BARRIER"
    atr_period: int = 14
    take_profit_atr: float = 1.5
    stop_loss_atr: float = 1.0
    max_holding_bars: int = 16
    entry_rule: str = "NEXT_BAR_OPEN"
    ambiguous_touch_policy: str = "EXCLUDE"
    version: str = "XAUUSD_OUTCOME_V1"

    def __post_init__(self) -> None:
        if self.method != "ATR_TRIPLE_BARRIER":
            raise XAUUSDResearchError("unsupported outcome method")
        if self.entry_rule != "NEXT_BAR_OPEN":
            raise XAUUSDResearchError("entry_rule must be NEXT_BAR_OPEN")
        if self.ambiguous_touch_policy not in {"EXCLUDE", "CONSERVATIVE_SL_FIRST"}:
            raise XAUUSDResearchError("unsupported ambiguous_touch_policy")
        if isinstance(self.atr_period, bool) or self.atr_period <= 0:
            raise XAUUSDResearchError("atr_period must be positive")
        if isinstance(self.max_holding_bars, bool) or self.max_holding_bars <= 0:
            raise XAUUSDResearchError("max_holding_bars must be positive")
        for name, value in (
            ("take_profit_atr", self.take_profit_atr),
            ("stop_loss_atr", self.stop_loss_atr),
        ):
            if not math.isfinite(float(value)) or float(value) <= 0:
                raise XAUUSDResearchError(f"{name} must be finite and positive")
        if not self.version.strip():
            raise XAUUSDResearchError("outcome spec version is required")


@dataclass(frozen=True)
class XAUUSDResearchRequest:
    """Immutable request snapshot for one M15 decision event."""

    run_id: str
    instrument: str
    decision_time: datetime
    dataset_version: str
    config_version: str
    outcome_spec: OutcomeSpec = field(default_factory=OutcomeSpec)
    decision_timeframe: str = DECISION_TIMEFRAME
    context_timeframes: tuple[str, ...] = CONTEXT_TIMEFRAMES
    model_version: str | None = None

    def __post_init__(self) -> None:
        if self.instrument != "XAUUSD":
            raise XAUUSDResearchError("V1 supports XAUUSD only")
        if self.decision_timeframe != DECISION_TIMEFRAME:
            raise XAUUSDResearchError("V1 decision timeframe must be M15")
        if tuple(self.context_timeframes) != CONTEXT_TIMEFRAMES:
            raise XAUUSDResearchError(
                f"context_timeframes must be {CONTEXT_TIMEFRAMES!r} in canonical order"
            )
        _require_aware(self.decision_time, "decision_time")
        for name, value in (
            ("run_id", self.run_id),
            ("dataset_version", self.dataset_version),
            ("config_version", self.config_version),
        ):
            if not value.strip():
                raise XAUUSDResearchError(f"{name} is required")


@dataclass(frozen=True)
class EvidenceRecord:
    """Canonical, time-bounded evidence emitted by an existing engine adapter."""

    evidence_id: str
    engine_name: str
    instrument: str
    as_of: datetime
    timeframe: str
    feature_name: str
    value: float | int | str | bool | None
    direction: int = 0
    strength: float = 0.0
    quality: float = 1.0
    dependency_group: str = ""
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_aware(self.as_of, "evidence.as_of")
        for name, value in (
            ("evidence_id", self.evidence_id),
            ("engine_name", self.engine_name),
            ("instrument", self.instrument),
            ("feature_name", self.feature_name),
        ):
            if not value.strip():
                raise XAUUSDResearchError(f"{name} is required")
        if self.timeframe not in SUPPORTED_TIMEFRAMES:
            raise XAUUSDResearchError(f"unsupported evidence timeframe: {self.timeframe}")
        if self.direction not in (-1, 0, 1):
            raise XAUUSDResearchError("direction must be -1, 0, or 1")
        for name, value in (("strength", self.strength), ("quality", self.quality)):
            if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                raise XAUUSDResearchError(f"{name} must be finite and within [0, 1]")
        if isinstance(self.value, (float, int)) and not isinstance(self.value, bool):
            if not math.isfinite(float(self.value)):
                raise XAUUSDResearchError("numeric evidence value must be finite")


@dataclass(frozen=True)
class EngineResult:
    """Recorded result from one adapter, including non-success states."""

    engine_name: str
    status: EngineStatus
    evidence: tuple[EvidenceRecord, ...] = ()
    reason_codes: tuple[str, ...] = ()
    engine_version: str = "UNSPECIFIED"


EngineAdapter = Callable[[XAUUSDResearchRequest, Any], EngineResult]


@dataclass(frozen=True)
class XAUUSDResearchResult:
    """Auditable collection-stage result; not a trading recommendation."""

    request: XAUUSDResearchRequest
    status: ResearchStatus
    engine_results: tuple[EngineResult, ...]
    evidence: tuple[EvidenceRecord, ...]
    missing_required_engines: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.request.run_id,
            "instrument": self.request.instrument,
            "decision_time": self.request.decision_time.isoformat(),
            "decision_timeframe": self.request.decision_timeframe,
            "context_timeframes": list(self.request.context_timeframes),
            "dataset_version": self.request.dataset_version,
            "config_version": self.request.config_version,
            "outcome_spec": {
                "method": self.request.outcome_spec.method,
                "atr_period": self.request.outcome_spec.atr_period,
                "take_profit_atr": self.request.outcome_spec.take_profit_atr,
                "stop_loss_atr": self.request.outcome_spec.stop_loss_atr,
                "max_holding_bars": self.request.outcome_spec.max_holding_bars,
                "entry_rule": self.request.outcome_spec.entry_rule,
                "ambiguous_touch_policy": self.request.outcome_spec.ambiguous_touch_policy,
                "version": self.request.outcome_spec.version,
            },
            "status": self.status.value,
            "engine_results": [
                {
                    "engine_name": item.engine_name,
                    "engine_version": item.engine_version,
                    "status": item.status.value,
                    "reason_codes": list(item.reason_codes),
                    "evidence_ids": [record.evidence_id for record in item.evidence],
                }
                for item in self.engine_results
            ],
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "engine_name": item.engine_name,
                    "instrument": item.instrument,
                    "as_of": item.as_of.isoformat(),
                    "timeframe": item.timeframe,
                    "feature_name": item.feature_name,
                    "value": item.value,
                    "direction": item.direction,
                    "strength": item.strength,
                    "quality": item.quality,
                    "dependency_group": item.dependency_group,
                    "source_refs": list(item.source_refs),
                }
                for item in self.evidence
            ],
            "missing_required_engines": list(self.missing_required_engines),
            "reason_codes": list(self.reason_codes),
            "probabilities": None,
            "execution_enabled": False,
        }


class XAUUSDResearchOrchestrator:
    """Run injected engines without changing their existing implementation.

    Required engine names are configured by the caller from the repository
    audit. Missing/failed required adapters fail closed. Optional adapter
    failures are preserved in the result and do not erase valid evidence.
    """

    def __init__(
        self,
        adapters: Mapping[str, EngineAdapter],
        *,
        required_engines: tuple[str, ...] = (),
    ) -> None:
        normalized = dict(adapters)
        if any(not name.strip() for name in normalized):
            raise XAUUSDResearchError("adapter names must be non-empty")
        if len(normalized) != len(adapters):
            raise XAUUSDResearchError("adapter names must be unique")
        if any(not name.strip() for name in required_engines):
            raise XAUUSDResearchError("required engine names must be non-empty")
        if len(set(required_engines)) != len(required_engines):
            raise XAUUSDResearchError("required engine names must be unique")
        self._adapters = normalized
        self._required_engines = tuple(sorted(required_engines))

    def run(self, request: XAUUSDResearchRequest, market_snapshot: Any) -> XAUUSDResearchResult:
        results: list[EngineResult] = []
        accepted_evidence: list[EvidenceRecord] = []
        reasons: list[str] = []
        missing_required: list[str] = []

        for engine_name in sorted(set(self._adapters) | set(self._required_engines)):
            adapter = self._adapters.get(engine_name)
            if adapter is None:
                results.append(
                    EngineResult(
                        engine_name=engine_name,
                        status=EngineStatus.NOT_CONFIGURED,
                        reason_codes=("REQUIRED_ENGINE_NOT_CONFIGURED",),
                    )
                )
                missing_required.append(engine_name)
                reasons.append(f"REQUIRED_ENGINE_NOT_CONFIGURED:{engine_name}")
                continue

            try:
                result = adapter(request, market_snapshot)
                if not isinstance(result, EngineResult):
                    raise XAUUSDResearchError("adapter returned a non-EngineResult value")
                if result.engine_name != engine_name:
                    raise XAUUSDResearchError("adapter engine_name does not match registry key")
                if result.status == EngineStatus.OK:
                    for record in result.evidence:
                        if record.engine_name != engine_name:
                            raise XAUUSDResearchError("evidence engine_name does not match adapter")
                        if record.instrument != request.instrument:
                            raise XAUUSDResearchError("evidence instrument does not match request")
                        if record.as_of > request.decision_time:
                            raise XAUUSDResearchError("future evidence violates as-of boundary")
                else:
                    if result.evidence:
                        raise XAUUSDResearchError(
                            "non-OK engine results must not publish usable evidence"
                        )
            except Exception as exc:
                result = EngineResult(
                    engine_name=engine_name,
                    status=EngineStatus.FAILED,
                    reason_codes=(f"ADAPTER_CONTRACT_FAILED:{type(exc).__name__}",),
                )

            results.append(result)
            reasons.extend(result.reason_codes)
            if result.status == EngineStatus.OK:
                accepted_evidence.extend(result.evidence)
            elif engine_name in self._required_engines:
                missing_required.append(engine_name)
                reasons.append(f"REQUIRED_ENGINE_{result.status.value}:{engine_name}")
            else:
                reasons.append(f"OPTIONAL_ENGINE_{result.status.value}:{engine_name}")

        # A collection-stage result must never be mistaken for calibrated probabilities.
        unique_ids = [item.evidence_id for item in accepted_evidence]
        if len(unique_ids) != len(set(unique_ids)):
            accepted_evidence = []
            reasons.append("DUPLICATE_EVIDENCE_ID")
        if not accepted_evidence:
            reasons.append("NO_VALID_EVIDENCE")

        insufficient = bool(missing_required) or not accepted_evidence
        return XAUUSDResearchResult(
            request=request,
            status=(
                ResearchStatus.INSUFFICIENT_EVIDENCE
                if insufficient
                else ResearchStatus.EVIDENCE_COLLECTED
            ),
            engine_results=tuple(results),
            evidence=tuple(accepted_evidence),
            missing_required_engines=tuple(sorted(set(missing_required))),
            reason_codes=tuple(sorted(set(reasons))),
        )


__all__ = [
    "CONTEXT_TIMEFRAMES",
    "DECISION_TIMEFRAME",
    "EngineResult",
    "EngineStatus",
    "EvidenceRecord",
    "OutcomeLabel",
    "OutcomeSpec",
    "ResearchStatus",
    "SUPPORTED_TIMEFRAMES",
    "XAUUSDResearchError",
    "XAUUSDResearchOrchestrator",
    "XAUUSDResearchRequest",
    "XAUUSDResearchResult",
]
