"""Sequence-gated path from reconstructed market state to XAUUSD evidence.

This additive pipeline leaves feature calculations and research orchestration
unchanged. A caller must supply the complete raw event-clock stream in
ingestion order; sequence validity alone cannot prove source completeness.
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
from researchos.orchestration.validated_market_state_reconstruction import (
    ValidatedReconstructionResult,
    reconstruct_if_sequence_valid,
)
from researchos.orchestration.xauusd_market_state_adapter import (
    XAUUSDMarketStateEvidenceAdapter,
)
from researchos.orchestration.xauusd_research import (
    EngineResult,
    EngineStatus,
    XAUUSDResearchRequest,
)


@dataclass(frozen=True)
class MarketStateEvidencePipelineResult:
    """Auditable output from sequence gate, reconstruction, and evidence adapter."""

    reconstruction: ValidatedReconstructionResult
    evidence_result: EngineResult


def reconstruct_xauusd_evidence_if_sequence_valid(
    request: XAUUSDResearchRequest,
    engine: ParallelMarketStateEngine,
    *,
    event_clocks: Sequence[EventClock],
    quotes: Sequence[Quote] = (),
    books: Sequence[BookSnapshot] = (),
    trades: Sequence[TradePrint] = (),
    macro: Sequence[MacroPoint] = (),
    adapter: XAUUSDMarketStateEvidenceAdapter | None = None,
) -> MarketStateEvidencePipelineResult:
    """Validate source sequences before reconstruction and evidence adaptation.

    Invalid sequences block both reconstruction and evidence publication. A
    valid sequence permits the existing engine to run, after which the existing
    adapter independently enforces required source freshness and completeness.
    """
    reconstruction = reconstruct_if_sequence_valid(
        engine,
        event_clocks=event_clocks,
        symbol=request.instrument,
        decision_time_ns=int(request.decision_time.timestamp() * 1_000_000_000),
        quotes=quotes,
        books=books,
        trades=trades,
        macro=macro,
    )
    if reconstruction.status != "RECONSTRUCTED" or reconstruction.market_state is None:
        evidence_result = EngineResult(
            engine_name="market_state",
            status=EngineStatus.INSUFFICIENT,
            reason_codes=("SEQUENCE_INTEGRITY_FAILED",),
            engine_version="XAUUSD_SEQUENCE_GATED_EVIDENCE_V1",
        )
    else:
        evidence_result = (adapter or XAUUSDMarketStateEvidenceAdapter())(
            request, reconstruction.market_state
        )
    return MarketStateEvidencePipelineResult(
        reconstruction=reconstruction,
        evidence_result=evidence_result,
    )


__all__ = [
    "MarketStateEvidencePipelineResult",
    "reconstruct_xauusd_evidence_if_sequence_valid",
]
