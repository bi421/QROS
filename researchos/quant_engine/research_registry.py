"""
Research registry — additive registration of the certified analytical surface.

Phase 5.1 — Certified Analytical Compute Surface (WP-1).

This module wires the research backends (Python reference + C++ candidate)
into the existing ``BackendRouter`` using the frozen registration API.  It is
strictly additive:

    * ``create_research_router()`` — a ``BackendRouter`` with the Python
      reference backend and the C++ research candidate registered.
    * ``register_research_backend()`` — register a research backend as a
      candidate on an existing router.
    * ``create_research_engine()`` — a ``ResearchEngine`` over a research
      backend (Python reference by default; C++ candidate opt-in).

The ``BackendRouter`` already enforces the trust boundary: it rejects any
candidate that does not advertise determinism/statelessness/no-timestamps/
no-randomness/explicit-typing, validates candidate output against the Python
reference via ``NumericalComparator``, and automatically falls back to the
Python reference on any capability/execution/validation failure.

This is a certification/trust layer only — it computes no trading decisions.
"""

from __future__ import annotations

from researchos.quant_engine.backend import PythonQuantBackend
from researchos.quant_engine.interface import QuantComputationInterface
from researchos.quant_engine.research_cpp_backend import ResearchCppBackend
from researchos.quant_engine.research_engine import PythonResearchBackend, ResearchEngine
from researchos.quant_engine.research_interface import RESEARCH_OPERATIONS, ResearchComputationInterface
from researchos.quant_engine.router import BackendRouter


def register_research_backend(router: BackendRouter, backend: QuantComputationInterface) -> None:
    """Register a research backend as a candidate on an existing ``BackendRouter``.

    The backend must implement ``QuantComputationInterface`` (which the
    research backends do) so it passes the router's capability check.
    """
    router.register(backend)


def create_research_router(
    reference_backend: QuantComputationInterface | None = None,
    register_cpp: bool = True,
) -> BackendRouter:
    """Create a ``BackendRouter`` with the research analytical surface registered.

    Args:
        reference_backend: Optional custom reference backend (defaults to the
            Python reference ``PythonQuantBackend``).
        register_cpp: Whether to register the C++ research candidate.

    Returns:
        A ``BackendRouter`` with the Python reference backend and, optionally,
        the ``ResearchCppBackend`` candidate.
    """
    reference = reference_backend or PythonQuantBackend()
    router = BackendRouter(reference_backend=reference)
    if register_cpp:
        register_research_backend(router, ResearchCppBackend())
    return router


def create_research_engine(
    backend: ResearchComputationInterface | None = None,
    use_cpp: bool = False,
) -> ResearchEngine:
    """Create a ``ResearchEngine`` over a research backend.

    Args:
        backend: Optional explicit research backend (must implement the
            research ops).  Defaults to a Python reference backend.
        use_cpp: When True and no explicit ``backend`` is given, use the
            ``ResearchCppBackend`` candidate (which delegates base quant ops
            to C++ when available and falls back to Python otherwise).

    Returns:
        A ``ResearchEngine`` facade.
    """
    if backend is not None:
        return ResearchEngine(backend=backend)
    if use_cpp:
        return ResearchEngine(backend=ResearchCppBackend())
    return ResearchEngine(backend=PythonResearchBackend())


__all__ = [
    "RESEARCH_OPERATIONS",
    "register_research_backend",
    "create_research_router",
    "create_research_engine",
]
