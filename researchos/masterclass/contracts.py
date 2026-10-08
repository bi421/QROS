"""Immutable contracts for the six-part QROS MASTERCLASS architecture."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
from typing import Any


def _hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _unit(value: float, name: str) -> float:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1]")
    return float(value)


@dataclass(frozen=True)
class EconomicObservation:
    """One timestamped macro observation with explicit forecast surprise."""

    name: str
    timestamp: str
    actual: float
    expected: float | None = None
    previous: float | None = None
    source: str = ""
    unit: str = ""

    @property
    def surprise(self) -> float | None:
        if self.expected is None:
            return None
        return self.actual - self.expected

    @property
    def surprise_direction(self) -> int:
        s = self.surprise
        return 0 if s is None or s == 0 else (1 if s > 0 else -1)


@dataclass(frozen=True)
class MarketRelationship:
    """Observed cross-asset relationship; correlation is not causal proof."""

    source: str
    target: str
    correlation: float
    beta: float | None = None
    window: int = 0
    regime: str = ""
    direction: str = "neutral"

    def validate(self) -> None:
        if not -1.0 <= self.correlation <= 1.0:
            raise ValueError("correlation must be in [-1, 1]")
        if self.window < 0:
            raise ValueError("window must be non-negative")


@dataclass(frozen=True)
class TechnicalEvidence:
    """Technical/microstructure evidence with no implied trade outcome."""

    name: str
    direction: str
    strength: float
    confidence: float
    timestamp: str
    source: str = ""
    tags: tuple[str, ...] = ()

    def validate(self) -> None:
        _unit(self.strength, "strength")
        _unit(self.confidence, "confidence")


@dataclass(frozen=True)
class HumanState:
    """Explicitly supplied human-state observations; never inferred silently."""

    timestamp: str
    sleep_quality: float | None = None
    fatigue: float | None = None
    stress: float | None = None
    attention: float | None = None
    self_reported: bool = True

    def validate(self) -> None:
        for name in ("sleep_quality", "fatigue", "stress", "attention"):
            value = getattr(self, name)
            if value is not None:
                _unit(value, name)


@dataclass(frozen=True)
class TradeManagementPlan:
    """Risk/management plan; not a broker order."""

    entry: float
    stop_loss: float
    take_profit: float
    invalidation: str
    risk_amount: float
    position_size: float
    partial_target: float | None = None
    breakeven_trigger: float | None = None

    def validate(self) -> None:
        for name in ("entry", "stop_loss", "take_profit", "risk_amount", "position_size"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.risk_amount <= 0.0:
            raise ValueError("risk_amount must be positive")
        if self.position_size <= 0.0:
            raise ValueError("position_size must be positive")
        if not self.invalidation.strip():
            raise ValueError("invalidation must not be empty")


@dataclass(frozen=True)
class ConditionalOutcome:
    """Historical conditional outcome summary with explicit sample size."""

    condition_key: tuple[str, ...]
    bullish_wins: int
    bearish_wins: int
    neutral_outcomes: int = 0
    alpha: float = 1.0
    beta: float = 1.0

    def validate(self) -> None:
        if any(v < 0 for v in (self.bullish_wins, self.bearish_wins, self.neutral_outcomes)):
            raise ValueError("outcome counts must be non-negative")
        if self.alpha <= 0 or self.beta <= 0:
            raise ValueError("smoothing parameters must be positive")

    @property
    def sample_size(self) -> int:
        return self.bullish_wins + self.bearish_wins + self.neutral_outcomes

    @property
    def bullish_probability(self) -> float:
        self.validate()
        total = self.sample_size + self.alpha + self.beta
        return (self.bullish_wins + self.alpha) / total

    @property
    def bearish_probability(self) -> float:
        self.validate()
        total = self.sample_size + self.alpha + self.beta
        return (self.bearish_wins + self.beta) / total


@dataclass(frozen=True)
class EvidenceBundle:
    """All six MASTERCLASS branches before Bayesian/quant fusion."""

    macro: tuple[EconomicObservation, ...] = ()
    relationships: tuple[MarketRelationship, ...] = ()
    technical: tuple[TechnicalEvidence, ...] = ()
    human: HumanState | None = None
    psychology: tuple[TechnicalEvidence, ...] = ()
    historical: ConditionalOutcome | None = None

    def validate(self) -> None:
        for relationship in self.relationships:
            relationship.validate()
        for item in (*self.technical, *self.psychology):
            item.validate()
        if self.human is not None:
            self.human.validate()
        if self.historical is not None:
            self.historical.validate()

    def content_hash(self) -> str:
        self.validate()
        return _hash({
            "macro": [x.__dict__ for x in self.macro],
            "relationships": [x.__dict__ for x in self.relationships],
            "technical": [x.__dict__ for x in self.technical],
            "human": None if self.human is None else self.human.__dict__,
            "psychology": [x.__dict__ for x in self.psychology],
            "historical": None if self.historical is None else self.historical.__dict__,
        })
