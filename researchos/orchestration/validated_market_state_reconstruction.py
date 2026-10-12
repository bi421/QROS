"""Fail-closed gate connecting sequence validation to market-state reconstruction.

Callers provide the canonical ingestion-ordered clock stream alongside the
feature inputs. This wrapper never sorts, repairs, or silently drops events.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from researchos.orchestration.market_state_reconstruction import (
    BookSnapshot,
    EventClock,
    MacroPoint,
    ParallelMarketStateEngine,
    Quote,
    TradePrint,
)
from researchos.orchestration.market_state_sequence_guard import (
    SequenceIntegrityReport,
    assess_sequence_integrity,
)


@dataclass(frozen=True)
class ValidatedReconstructionResult:
    """Result that makes sequence-integrity failure explicit."""

    status: str
    sequence_integrity: SequenceIntegrityReport
    market_state: dict[str, object] | None


def reconstruct_if_sequence_valid(
    engine: ParallelMarketStateEngine,
    *,
    event_clocks: Sequence[EventClock],
    symbol: str,
    decision_time_ns: int,
    quotes: Sequence[Quote] = (),
    books: Sequence[BookSnapshot] = (),
    trades: Sequence[TradePrint] = (),
    macro: Sequence[MacroPoint] = (),
) -> ValidatedReconstructionResult:
    """Run reconstruction only when the supplied ingestion stream is intact.

    The event_clocks argument must represent the raw source events used by the
    caller, in ingestion order. This function cannot independently prove that
    callers supplied every raw event; that provenance remains an integration
    responsibility.
    """
    report = assess_sequence_integrity(event_clocks)
    if not report.valid:
        return ValidatedReconstructionResult(
            status="SEQUENCE_INTEGRITY_FAILED",
            sequence_integrity=report,
            market_state=None,
        )

    state = engine.reconstruct(
        symbol=symbol,
        decision_time_ns=decision_time_ns,
        quotes=quotes,
        books=books,
        trades=trades,
        macro=macro,
    )
    return ValidatedReconstructionResult(
        status="RECONSTRUCTED",
        sequence_integrity=report,
        market_state=state,
    )


__all__ = ["ValidatedReconstructionResult", "reconstruct_if_sequence_valid"]
