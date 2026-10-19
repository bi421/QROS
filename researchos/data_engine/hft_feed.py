"""Strict parser for the HFT -> QROS read-only XAUUSD quote-snapshot handoff.

This is a snapshot contract, not a tick-stream adapter, historical candle loader,
sequence-integrity proof, trading signal, or order-execution interface.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "qros.hft.xauusd.quote-snapshot.v1"


class HFTQuoteSnapshotError(ValueError):
    """Raised when a handoff snapshot is malformed, stale, or unverifiable."""


@dataclass(frozen=True, slots=True)
class HFTQuoteSnapshot:
    symbol: str
    provider: str
    event_time_utc: datetime
    ingest_time_utc: datetime
    bid: float
    ask: float
    spread: float
    tick_age_seconds_at_probe: float
    payload_sha256: str
    sequence: None = None
    source_kind: str = "MT5_symbol_info_tick_snapshot"

    @property
    def mid_price(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def is_continuous_stream(self) -> bool:
        return False


def _aware_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise HFTQuoteSnapshotError(f"{field} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HFTQuoteSnapshotError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HFTQuoteSnapshotError(f"{field} must include an explicit timezone")
    return parsed.astimezone(timezone.utc)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HFTQuoteSnapshotError("payload cannot be canonically serialized") from exc
    return hashlib.sha256(raw).hexdigest()


def parse_hft_quote_snapshot(
    envelope: Mapping[str, Any],
    *,
    now: datetime | None = None,
    max_age_seconds: float = 15.0,
    future_tolerance_seconds: float = 2.0,
) -> HFTQuoteSnapshot:
    """Validate provenance, integrity, quote shape and current freshness; never persists data."""
    if not isinstance(envelope, Mapping) or envelope.get("schema") != SCHEMA or envelope.get("schema_version") != 1:
        raise HFTQuoteSnapshotError("unsupported or missing HFT handoff schema")
    payload = envelope.get("payload")
    digest = envelope.get("payload_sha256")
    if not isinstance(payload, Mapping) or not isinstance(digest, str) or len(digest) != 64:
        raise HFTQuoteSnapshotError("missing payload or SHA-256 digest")
    if _canonical_sha256(payload) != digest:
        raise HFTQuoteSnapshotError("payload SHA-256 mismatch")
    if payload.get("symbol") != "XAUUSD":
        raise HFTQuoteSnapshotError("only XAUUSD snapshots are accepted")
    if payload.get("source_kind") != "MT5_symbol_info_tick_snapshot":
        raise HFTQuoteSnapshotError("unsupported source kind")
    if payload.get("timestamp_mode") != "pepperstone-server" or payload.get("feed_status") != "PASS_READ_ONLY":
        raise HFTQuoteSnapshotError("source timestamp/feed status is not approved")
    provider = payload.get("provider")
    if not isinstance(provider, str) or "pepperstone" not in provider.lower():
        raise HFTQuoteSnapshotError("provider identity is not an approved Pepperstone server")
    if payload.get("sequence") is not None:
        raise HFTQuoteSnapshotError("snapshot adapter does not accept unverifiable sequence claims")
    bid, ask, spread, probe_age = (payload.get("bid"), payload.get("ask"),
                                   payload.get("spread"), payload.get("tick_age_seconds_at_probe"))
    values = (bid, ask, spread, probe_age)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise HFTQuoteSnapshotError("quote values must be numeric")
    if not all(math.isfinite(value) for value in values):
        raise HFTQuoteSnapshotError("quote values must be finite")
    if bid <= 0 or ask < bid or spread < 0 or not math.isclose(ask - bid, spread, rel_tol=0, abs_tol=1e-8):
        raise HFTQuoteSnapshotError("bid/ask/spread invariant failed")
    if probe_age < -future_tolerance_seconds or probe_age > max_age_seconds:
        raise HFTQuoteSnapshotError("probe-time quote freshness failed")
    event_time = _aware_utc(payload.get("event_time_utc"), "event_time_utc")
    ingest_time = _aware_utc(payload.get("ingest_time_utc"), "ingest_time_utc")
    created_at = _aware_utc(envelope.get("created_at_utc"), "created_at_utc")
    if created_at != ingest_time:
        raise HFTQuoteSnapshotError("envelope creation time does not match payload ingest time")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise HFTQuoteSnapshotError("now must be timezone-aware")
    current = current.astimezone(timezone.utc)
    age = (current - event_time).total_seconds()
    if age < -future_tolerance_seconds:
        raise HFTQuoteSnapshotError("event timestamp is too far in the future")
    if age > max_age_seconds:
        raise HFTQuoteSnapshotError("snapshot expired before QROS ingestion")
    if (ingest_time - event_time).total_seconds() < -future_tolerance_seconds:
        raise HFTQuoteSnapshotError("ingest timestamp precedes event time beyond tolerance")
    return HFTQuoteSnapshot(
        symbol="XAUUSD", provider=provider, event_time_utc=event_time,
        ingest_time_utc=ingest_time, bid=float(bid), ask=float(ask), spread=float(spread),
        tick_age_seconds_at_probe=float(probe_age), payload_sha256=digest,
    )


def load_hft_quote_snapshot(path: str | Path, **kwargs: Any) -> HFTQuoteSnapshot:
    """Read and validate one snapshot from a local file handoff."""
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            value = json.load(handle, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise HFTQuoteSnapshotError(f"cannot read valid JSON snapshot: {exc}") from exc
    if not isinstance(value, Mapping):
        raise HFTQuoteSnapshotError("snapshot root must be a JSON object")
    return parse_hft_quote_snapshot(value, **kwargs)
