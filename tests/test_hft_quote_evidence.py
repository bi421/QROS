from datetime import datetime, timezone

import pytest

from researchos.data_engine.hft_feed import HFTQuoteSnapshot
from researchos.evidence.envelope import ARTIFACT_TYPES
from researchos.evidence.hft_quote_emission import emit_hft_quote_snapshot
from researchos.evidence.repository import EvidenceRepository


def make_snapshot():
    return HFTQuoteSnapshot(
        symbol="XAUUSD",
        provider="Pepperstone-Demo",
        event_time_utc=datetime(2026, 10, 19, 13, 45, tzinfo=timezone.utc),
        ingest_time_utc=datetime(2026, 10, 19, 13, 45, 1, tzinfo=timezone.utc),
        bid=4152.81,
        ask=4152.98,
        spread=0.17,
        tick_age_seconds_at_probe=0.5,
        payload_sha256="a" * 64,
    )


def test_quote_snapshot_is_first_class_qros_evidence_with_lineage_hashes():
    repo = EvidenceRepository()
    snapshot = make_snapshot()
    envelope = emit_hft_quote_snapshot(snapshot, repository=repo)

    assert "QuoteSnapshot" in ARTIFACT_TYPES
    assert envelope.artifact_type == "QuoteSnapshot"
    assert envelope.verify() is True
    assert envelope.artifact_hash
    assert envelope.lineage_hash
    assert envelope.created_at == snapshot.ingest_time_utc.isoformat()
    assert envelope.payload["source_payload_sha256"] == snapshot.payload_sha256
    assert envelope.payload["qros_quote"]["mid"] == pytest.approx(4152.895)
    assert envelope.payload["qros_quote"]["bid_size"] == 0.0
    assert envelope.payload["sequence"] is None
    assert envelope.payload["continuous_stream"] is False

    stored = repo.get_artifact(envelope.artifact_hash)
    assert stored is not None
    assert stored.to_dict() == envelope.to_dict()


def test_emitter_rejects_unvalidated_input():
    with pytest.raises(TypeError, match="validated HFTQuoteSnapshot"):
        emit_hft_quote_snapshot({"symbol": "XAUUSD"}, repository=EvidenceRepository())


def test_emitter_requires_explicit_repository():
    with pytest.raises(TypeError):
        emit_hft_quote_snapshot(make_snapshot())
