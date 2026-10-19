"""Emit validated HFT quote snapshots into QROS's evidence/lineage store."""
from __future__ import annotations

from researchos.data_engine.hft_feed import HFTQuoteSnapshot
from researchos.data_engine.hft_quote_adapter import snapshot_to_quote
from researchos.evidence.envelope import EvidenceEnvelope, build_envelope
from researchos.evidence.repository import EvidenceRepository

ARTIFACT_TYPE = "QuoteSnapshot"
ARTIFACT_VERSION = "1.0.0"


def emit_hft_quote_snapshot(
    snapshot: HFTQuoteSnapshot,
    *,
    repository: EvidenceRepository,
) -> EvidenceEnvelope:
    """Append a validated snapshot as a first-class QROS evidence artifact.

    A repository must be supplied explicitly so this function cannot silently
    pretend that an in-memory store is durable. The snapshot's own SHA-256 is
    retained inside the evidence payload; the envelope adds QROS artifact and
    lineage hashes. This does not create a historical dataset or trading signal.
    """
    if not isinstance(snapshot, HFTQuoteSnapshot):
        raise TypeError("snapshot must be a validated HFTQuoteSnapshot")
    if not isinstance(repository, EvidenceRepository):
        raise TypeError("repository must be an EvidenceRepository")

    quote = snapshot_to_quote(snapshot)
    payload = {
        "schema": "qros.hft.xauusd.quote-snapshot-evidence.v1",
        "symbol": snapshot.symbol,
        "provider": snapshot.provider,
        "source_kind": snapshot.source_kind,
        "event_time_utc": snapshot.event_time_utc.isoformat(),
        "ingest_time_utc": snapshot.ingest_time_utc.isoformat(),
        "bid": snapshot.bid,
        "ask": snapshot.ask,
        "mid_price": snapshot.mid_price,
        "spread": snapshot.spread,
        "tick_age_seconds_at_probe": snapshot.tick_age_seconds_at_probe,
        "source_payload_sha256": snapshot.payload_sha256,
        "qros_quote": {
            "symbol": quote.symbol,
            "timestamp_utc": quote.timestamp.isoformat(),
            "bid": quote.bid,
            "ask": quote.ask,
            "mid": quote.mid,
            "spread": quote.spread,
            "bid_size": quote.bid_size,
            "ask_size": quote.ask_size,
            "exchange": quote.exchange,
            "condition": quote.condition,
        },
        "sequence": None,
        "continuous_stream": False,
        "limitations": [
            "single quote snapshot; not a continuous tick stream",
            "not historical OHLCV and not a dataset",
            "bid/ask sizes and trade volume are unavailable, not zero in the market",
            "provider sequence integrity is not established",
            "source payload SHA-256 is integrity evidence, not producer authentication",
            "feed health does not establish order-execution venue health",
        ],
    }
    envelope = build_envelope(
        ARTIFACT_TYPE,
        payload,
        version=ARTIFACT_VERSION,
        created_at=snapshot.ingest_time_utc.isoformat(),
    )
    return repository.append_artifact(envelope)
