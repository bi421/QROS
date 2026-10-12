"""Fail-closed bridge from reconstructed market state into canonical XAUUSD evidence.

The adapter does not fetch feeds, change existing engine calculations, calculate
probabilities, or enable execution. All required sources must be fresh before
any evidence is published, avoiding a partial-state result being mistaken for a
complete market snapshot.
"""
from __future__ import annotations

import math
from datetime import timedelta
from typing import Any, Mapping

from researchos.orchestration.xauusd_research import (
    DECISION_TIMEFRAME,
    EngineResult,
    EngineStatus,
    EvidenceRecord,
    XAUUSDResearchRequest,
)


_REQUIRED = (
    ("broker_quote", None),
    ("futures_order_book", None),
    ("futures_trade_flow", None),
    ("macro", "DXY"),
    ("macro", "VXY"),
)

_NUMERIC_FIELDS: dict[tuple[str, str | None], tuple[str, ...]] = {
    ("broker_quote", None): ("mid_price", "spread", "spread_bps", "top_size_imbalance"),
    ("futures_order_book", None): ("bid_depth", "ask_depth", "depth_imbalance"),
    ("futures_trade_flow", None): ("total_volume", "signed_volume", "signed_volume_imbalance"),
    ("macro", "DXY"): ("value", "return_since_previous"),
    ("macro", "VXY"): ("value", "return_since_previous"),
}
_DIRECTIONAL = {
    "top_size_imbalance", "depth_imbalance", "signed_volume_imbalance",
    "return_since_previous",
}


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


class XAUUSDMarketStateEvidenceAdapter:
    """Convert one complete, fresh reconstruction into canonical evidence."""

    engine_name = "market_state"
    engine_version = "XAUUSD_MARKET_STATE_EVIDENCE_V1"

    def __call__(
        self, request: XAUUSDResearchRequest, market_state: object
    ) -> EngineResult:
        if not isinstance(market_state, Mapping):
            return self._insufficient("MARKET_STATE_NOT_MAPPING")
        if market_state.get("instrument") != request.instrument:
            return self._insufficient("INSTRUMENT_MISMATCH")
        if request.instrument != "XAUUSD":
            return self._insufficient("UNSUPPORTED_INSTRUMENT")

        decision_ns = _finite_number(market_state.get("decision_time_ns"))
        if decision_ns is None or decision_ns <= 0:
            return self._insufficient("INVALID_DECISION_TIMESTAMP")
        expected_ns = request.decision_time.timestamp() * 1_000_000_000
        if abs(decision_ns - expected_ns) > 1_000_000:
            return self._insufficient("DECISION_TIMESTAMP_MISMATCH")

        features = market_state.get("features")
        if not isinstance(features, Mapping):
            return self._insufficient("MARKET_STATE_FEATURES_MISSING")

        for section, instrument in _REQUIRED:
            group = features.get(section)
            item = group.get(instrument) if instrument else group
            if not isinstance(item, Mapping):
                return self._insufficient(f"SOURCE_MISSING:{section}:{instrument or 'default'}")
            if item.get("status") != "OK":
                return self._insufficient(f"SOURCE_NOT_READY:{section}:{instrument or 'default'}")
            if section != "macro":
                clock = item.get("clock")
                if not isinstance(clock, Mapping) or clock.get("fresh") is not True:
                    return self._insufficient(f"SOURCE_NOT_FRESH:{section}")
            else:
                clock = item.get("clock")
                if not isinstance(clock, Mapping) or clock.get("fresh") is not True:
                    return self._insufficient(f"SOURCE_NOT_FRESH:macro:{instrument}")

        records: list[EvidenceRecord] = []
        for (section, instrument), field_names in _NUMERIC_FIELDS.items():
            group = features[section]
            item = group[instrument] if instrument else group
            clock = item["clock"]
            age_ms = _finite_number(clock.get("event_age_ms"))
            source = clock.get("source")
            if age_ms is None or age_ms < 0 or not isinstance(source, str) or not source.strip():
                return self._insufficient(f"SOURCE_CLOCK_INVALID:{section}:{instrument or 'default'}")
            as_of = request.decision_time - timedelta(milliseconds=age_ms)
            for field_name in field_names:
                value = _finite_number(item.get(field_name))
                if value is None:
                    # A first macro observation has no return; that is absence of
                    # evidence, not a fabricated zero.
                    continue
                direction = 0
                if field_name in _DIRECTIONAL:
                    direction = 1 if value > 0 else -1 if value < 0 else 0
                evidence_id = (
                    f"{request.run_id}:market-state:{section}:"
                    f"{instrument or 'XAUUSD'}:{field_name}"
                )
                records.append(
                    EvidenceRecord(
                        evidence_id=evidence_id,
                        engine_name=self.engine_name,
                        instrument=request.instrument,
                        as_of=as_of,
                        timeframe=DECISION_TIMEFRAME,
                        feature_name=f"{instrument + '_' if instrument else ''}{field_name}",
                        value=value,
                        direction=direction,
                        strength=min(abs(value), 1.0) if field_name in _DIRECTIONAL else 0.0,
                        quality=1.0,
                        dependency_group=(
                            "macro-market" if section == "macro" else "microstructure"
                        ),
                        source_refs=(source, f"decision_time_ns:{int(decision_ns)}"),
                    )
                )

        if not records:
            return self._insufficient("NO_VALID_MARKET_STATE_EVIDENCE")
        return EngineResult(
            engine_name=self.engine_name,
            status=EngineStatus.OK,
            evidence=tuple(records),
            engine_version=self.engine_version,
        )

    def _insufficient(self, reason: str) -> EngineResult:
        return EngineResult(
            engine_name=self.engine_name,
            status=EngineStatus.INSUFFICIENT,
            reason_codes=(reason,),
            engine_version=self.engine_version,
        )


__all__ = ["XAUUSDMarketStateEvidenceAdapter"]
