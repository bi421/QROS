"""Adapter from a validated HFT snapshot to QROS's existing Quote object."""
from __future__ import annotations

from researchos.data_engine.hft_feed import HFTQuoteSnapshot
from researchos.data_engine.quote import Quote


def snapshot_to_quote(snapshot: HFTQuoteSnapshot) -> Quote:
    """Map price fields only; never infer size, volume, side, or a trade event.

    Keep the HFTQuoteSnapshot alongside this Quote when storing evidence because
    the Quote model has no dedicated payload-digest field.
    """
    if not isinstance(snapshot, HFTQuoteSnapshot):
        raise TypeError("snapshot must be a validated HFTQuoteSnapshot")
    return Quote(
        symbol=snapshot.symbol,
        timestamp=snapshot.event_time_utc,
        bid=snapshot.bid,
        ask=snapshot.ask,
        bid_size=0.0,
        ask_size=0.0,
        exchange=snapshot.provider,
        condition="read-only-snapshot; sequence-unavailable; sizes-unavailable",
    )
