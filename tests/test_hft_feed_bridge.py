from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from researchos.data_engine.hft_feed import (
    HFTQuoteSnapshotError,
    parse_hft_quote_snapshot,
)

NOW = datetime(2026, 10, 19, 13, 45, 0, tzinfo=timezone.utc)


def make_envelope():
    payload = {
        "symbol": "XAUUSD",
        "provider": "Pepperstone-Demo",
        "source_kind": "MT5_symbol_info_tick_snapshot",
        "event_time_utc": (NOW - timedelta(seconds=0.5)).isoformat(),
        "ingest_time_utc": NOW.isoformat(),
        "bid": 4152.81,
        "ask": 4152.98,
        "spread": 0.17,
        "tick_age_seconds_at_probe": 0.5,
        "digits": 2,
        "point": 0.01,
        "raw_time_msc": 1792417500000,
        "timestamp_mode": "pepperstone-server",
        "feed_status": "PASS_READ_ONLY",
        "sequence": None,
        "limitations": ["single quote snapshot; not a continuous tick stream"],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")
    return {
        "schema": "qros.hft.xauusd.quote-snapshot.v1",
        "schema_version": 1,
        "created_at_utc": NOW.isoformat(),
        "payload_sha256": hashlib.sha256(canonical).hexdigest(),
        "payload": payload,
    }


def test_accepts_fresh_integrity_checked_xauusd_snapshot():
    result = parse_hft_quote_snapshot(make_envelope(), now=NOW)
    assert result.symbol == "XAUUSD"
    assert result.mid_price == pytest.approx(4152.895)
    assert result.is_continuous_stream is False
    assert result.sequence is None
    assert len(result.payload_sha256) == 64


def test_rejects_tampered_payload_hash():
    envelope = make_envelope()
    envelope["payload"]["bid"] = 1.0
    with pytest.raises(HFTQuoteSnapshotError, match="SHA-256"):
        parse_hft_quote_snapshot(envelope, now=NOW)


@pytest.mark.parametrize("mutation,reason", [
    (lambda p: p.update(symbol="EURUSD"), "only XAUUSD"),
    (lambda p: p.update(provider="Other-Demo"), "provider identity"),
    (lambda p: p.update(timestamp_mode="raw-utc"), "timestamp/feed status"),
    (lambda p: p.update(feed_status="FAIL_CLOSED"), "timestamp/feed status"),
    (lambda p: p.update(sequence=42), "sequence claims"),
])
def test_rejects_invalid_provenance_and_payload(mutation, reason):
    envelope = make_envelope()
    mutation(envelope["payload"])
    envelope["payload_sha256"] = hashlib.sha256(
        json.dumps(envelope["payload"], sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()
    with pytest.raises(HFTQuoteSnapshotError, match=reason):
        parse_hft_quote_snapshot(envelope, now=NOW)


def test_rejects_stale_snapshot_at_qros_ingestion():
    envelope = make_envelope()
    old = NOW - timedelta(seconds=30)
    envelope["payload"]["event_time_utc"] = old.isoformat()
    envelope["payload"]["ingest_time_utc"] = NOW.isoformat()
    envelope["payload"]["tick_age_seconds_at_probe"] = 0.5
    envelope["created_at_utc"] = NOW.isoformat()
    payload = envelope["payload"]
    envelope["payload_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()
    with pytest.raises(HFTQuoteSnapshotError, match="expired"):
        parse_hft_quote_snapshot(envelope, now=NOW)


def test_rejects_future_timestamp():
    envelope = make_envelope()
    envelope["payload"]["event_time_utc"] = (NOW + timedelta(seconds=10)).isoformat()
    envelope["payload"]["ingest_time_utc"] = NOW.isoformat()
    envelope["payload_sha256"] = hashlib.sha256(
        json.dumps(envelope["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()
    with pytest.raises(HFTQuoteSnapshotError, match="future"):
        parse_hft_quote_snapshot(envelope, now=NOW)
