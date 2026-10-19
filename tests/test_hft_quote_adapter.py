from datetime import datetime, timezone

import pytest

from researchos.data_engine.hft_feed import HFTQuoteSnapshot
from researchos.data_engine.hft_quote_adapter import snapshot_to_quote


def test_adapter_maps_snapshot_to_existing_qros_quote_without_inventing_size():
    snapshot = HFTQuoteSnapshot(
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
    quote = snapshot_to_quote(snapshot)
    assert quote.symbol == "XAUUSD"
    assert quote.timestamp == snapshot.event_time_utc
    assert quote.bid == 4152.81
    assert quote.ask == 4152.98
    assert quote.mid == pytest.approx(4152.895)
    assert quote.spread == pytest.approx(0.17)
    assert quote.bid_size == 0.0
    assert quote.ask_size == 0.0
    assert "sequence-unavailable" in quote.condition


def test_adapter_rejects_arbitrary_unvalidated_object():
    with pytest.raises(TypeError, match="validated HFTQuoteSnapshot"):
        snapshot_to_quote({"symbol": "XAUUSD"})
