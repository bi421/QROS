"""Immutable, content-addressed definitions for Market Structure variants.

A StructureDefinition captures every registered parameter and fixed V1 rule.
It contains no market data and cannot execute a backtest or place an order.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import itertools
import json
import math
from typing import Any, Literal

BreakBasis = Literal["wick", "close"]
ChochRule = Literal["opposite_confirmed_swing_break"]
TrendFilter = Literal["off"]

_ALLOWED_FIELDS = frozenset(
    {
        "variant_key",
        "swing_window",
        "break_basis",
        "confirmation_bars",
        "break_buffer_atr",
        "atr_period",
        "choch_rule",
        "trend_filter",
    }
)


@dataclass(frozen=True, slots=True)
class StructureDefinition:
    """Immutable and deterministically hashable Market Structure definition."""

    swing_window: int
    break_basis: BreakBasis
    confirmation_bars: int
    break_buffer_atr: float
    atr_period: int
    choch_rule: ChochRule = "opposite_confirmed_swing_break"
    trend_filter: TrendFilter = "off"
    schema_version: str = "1.0.0"

    def __post_init__(self) -> None:
        for name, value in (
            ("swing_window", self.swing_window),
            ("confirmation_bars", self.confirmation_bars),
            ("atr_period", self.atr_period),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be an integer >= 1")

        if self.break_basis not in ("wick", "close"):
            raise ValueError("break_basis must be 'wick' or 'close'")
        if (
            isinstance(self.break_buffer_atr, bool)
            or not isinstance(self.break_buffer_atr, (int, float))
            or not math.isfinite(self.break_buffer_atr)
            or self.break_buffer_atr < 0
        ):
            raise ValueError("break_buffer_atr must be finite and >= 0")
        if self.choch_rule != "opposite_confirmed_swing_break":
            raise ValueError("unsupported V1 choch_rule")
        if self.trend_filter != "off":
            raise ValueError("unsupported V1 trend_filter")
        if not isinstance(self.schema_version, str) or not self.schema_version.strip():
            raise ValueError("schema_version must be a non-empty string")

        object.__setattr__(self, "break_buffer_atr", float(self.break_buffer_atr))

    @property
    def variant_key(self) -> str:
        buffer_bps = int(round(self.break_buffer_atr * 10_000))
        return (
            f"sw{self.swing_window:02d}_{self.break_basis}"
            f"_c{self.confirmation_bars}_atr{buffer_bps:04d}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh JSON-compatible representation of this definition."""
        return {
            "variant_key": self.variant_key,
            "swing_window": self.swing_window,
            "break_basis": self.break_basis,
            "confirmation_bars": self.confirmation_bars,
            "break_buffer_atr": self.break_buffer_atr,
            "atr_period": self.atr_period,
            "choch_rule": self.choch_rule,
            "trend_filter": self.trend_filter,
        }

    @property
    def canonical_json(self) -> str:
        """Canonical serialization used for deterministic content addressing."""
        payload = {"schema_version": self.schema_version, **self.to_dict()}
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )

    @property
    def definition_id(self) -> str:
        """SHA-256 of schema version and every field that defines V1 behaviour."""
        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        schema_version: str = "1.0.0",
    ) -> StructureDefinition:
        """Build from one preregistered grid row and verify its declared key."""
        keys = set(value)
        missing = _ALLOWED_FIELDS - keys
        unknown = keys - _ALLOWED_FIELDS
        if missing:
            raise ValueError(f"missing definition fields: {sorted(missing)}")
        if unknown:
            raise ValueError(f"unknown definition fields: {sorted(unknown)}")

        definition = cls(
            swing_window=value["swing_window"],
            break_basis=value["break_basis"],
            confirmation_bars=value["confirmation_bars"],
            break_buffer_atr=value["break_buffer_atr"],
            atr_period=value["atr_period"],
            choch_rule=value["choch_rule"],
            trend_filter=value["trend_filter"],
            schema_version=schema_version,
        )
        declared_key = value["variant_key"]
        if declared_key != definition.variant_key:
            raise ValueError(
                f"variant_key mismatch: declared={declared_key!r}, "
                f"derived={definition.variant_key!r}"
            )
        return definition


def definitions_from_grid_payload(
    payload: Mapping[str, Any],
) -> tuple[StructureDefinition, ...]:
    """Validate and materialize every immutable definition in a preregistered grid."""
    schema_version = payload.get("schema_version")
    variants = payload.get("variants")
    declared_count = payload.get("variant_count")

    if not isinstance(schema_version, str) or not schema_version.strip():
        raise ValueError("grid schema_version must be a non-empty string")
    if not isinstance(variants, Sequence) or isinstance(variants, (str, bytes)):
        raise ValueError("grid variants must be a sequence")
    if isinstance(declared_count, bool) or not isinstance(declared_count, int):
        raise ValueError("grid variant_count must be an integer")
    if declared_count != len(variants):
        raise ValueError(
            f"grid variant_count mismatch: declared={declared_count}, actual={len(variants)}"
        )

    definitions = tuple(
        StructureDefinition.from_mapping(item, schema_version=schema_version)
        for item in variants
        if isinstance(item, Mapping)
    )
    if len(definitions) != len(variants):
        raise ValueError("every grid variant must be a mapping")

    keys = [item.variant_key for item in definitions]
    ids = [item.definition_id for item in definitions]
    if len(set(keys)) != len(keys):
        raise ValueError("grid contains duplicate variant keys")
    if len(set(ids)) != len(ids):
        raise ValueError("grid contains duplicate definition IDs")

    axes = payload.get("axes")
    axis_fields = (
        "swing_window",
        "break_basis",
        "confirmation_bars",
        "break_buffer_atr",
        "atr_period",
        "choch_rule",
        "trend_filter",
    )
    if not isinstance(axes, Mapping) or set(axes) != set(axis_fields):
        raise ValueError("grid axes must declare every V1 definition field exactly once")

    axis_values: list[tuple[Any, ...]] = []
    for field in axis_fields:
        values = axes[field]
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not values:
            raise ValueError(f"grid axis {field} must be a non-empty sequence")
        if any(isinstance(item, bool) for item in values):
            raise ValueError(f"grid axis {field} cannot contain boolean values")
        if len(set(values)) != len(values):
            raise ValueError(f"grid axis {field} contains duplicate values")
        if {getattr(item, field) for item in definitions} != set(values):
            raise ValueError(f"grid axis {field} does not match variant definitions")
        axis_values.append(tuple(values))

    expected_combinations = set(itertools.product(*axis_values))
    actual_combinations = {
        tuple(getattr(item, field) for field in axis_fields) for item in definitions
    }
    if actual_combinations != expected_combinations:
        raise ValueError("grid variants do not contain the complete Cartesian product of axes")
    return definitions


__all__ = ["StructureDefinition", "definitions_from_grid_payload"]
