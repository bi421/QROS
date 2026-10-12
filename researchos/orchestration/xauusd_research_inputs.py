"""Composite input routing for the additive XAUUSD research orchestrator.

This module wires the existing technical/quant adapters and the typed macro
adapter without modifying their calculations. Market and macro inputs remain
separate typed snapshots; absent inputs are represented as NOT_CONFIGURED.
"""

from __future__ import annotations

from dataclasses import dataclass

from researchos.orchestration.xauusd_engine_adapters import (
    XAUUSDMarketSnapshot,
    XAUUSDQuantMathEvidenceAdapter,
    XAUUSDTechnicalEvidenceAdapter,
)
from researchos.orchestration.xauusd_macro_adapter import (
    XAUUSDMacroEvidenceAdapter,
    XAUUSDMacroSnapshot,
)
from researchos.orchestration.xauusd_research import (
    EngineResult,
    EngineStatus,
    XAUUSDResearchOrchestrator,
    XAUUSDResearchRequest,
    XAUUSDResearchResult,
)


@dataclass(frozen=True)
class XAUUSDResearchInputs:
    """Separate market OHLCV and pre-assessed macro snapshots for one run."""

    market: XAUUSDMarketSnapshot | None = None
    macro: XAUUSDMacroSnapshot | None = None


def _not_configured(engine_name: str, reason: str) -> EngineResult:
    return EngineResult(
        engine_name=engine_name,
        status=EngineStatus.NOT_CONFIGURED,
        reason_codes=(reason,),
    )


def _technical(request: XAUUSDResearchRequest, raw_inputs: object) -> EngineResult:
    if not isinstance(raw_inputs, XAUUSDResearchInputs) or raw_inputs.market is None:
        return _not_configured("technical", "XAUUSD_MARKET_SNAPSHOT_NOT_CONFIGURED")
    return XAUUSDTechnicalEvidenceAdapter()(request, raw_inputs.market)


def _quant_math(request: XAUUSDResearchRequest, raw_inputs: object) -> EngineResult:
    if not isinstance(raw_inputs, XAUUSDResearchInputs) or raw_inputs.market is None:
        return _not_configured("quant_math", "XAUUSD_MARKET_SNAPSHOT_NOT_CONFIGURED")
    return XAUUSDQuantMathEvidenceAdapter()(request, raw_inputs.market)


def _macro(request: XAUUSDResearchRequest, raw_inputs: object) -> EngineResult:
    if not isinstance(raw_inputs, XAUUSDResearchInputs) or raw_inputs.macro is None:
        return _not_configured("macro", "XAUUSD_MACRO_SNAPSHOT_NOT_CONFIGURED")
    return XAUUSDMacroEvidenceAdapter()(request, raw_inputs.macro)


def build_xauusd_research_orchestrator(
    *,
    required_engines: tuple[str, ...] = ("technical", "quant_math", "macro"),
) -> XAUUSDResearchOrchestrator:
    """Build the default three-engine collector with caller-controlled requirements.

    The collector only gathers deterministic evidence. It does not generate
    calibrated TP/SL/TIMEOUT probabilities and never executes orders.
    """
    return XAUUSDResearchOrchestrator(
        {
            "technical": _technical,
            "quant_math": _quant_math,
            "macro": _macro,
        },
        required_engines=required_engines,
    )


def collect_xauusd_research(
    request: XAUUSDResearchRequest,
    inputs: XAUUSDResearchInputs,
    *,
    required_engines: tuple[str, ...] = ("technical", "quant_math", "macro"),
) -> XAUUSDResearchResult:
    """Collect evidence from configured inputs, preserving missing-engine reasons."""
    return build_xauusd_research_orchestrator(
        required_engines=required_engines,
    ).run(request, inputs)


__all__ = [
    "XAUUSDResearchInputs",
    "build_xauusd_research_orchestrator",
    "collect_xauusd_research",
]
