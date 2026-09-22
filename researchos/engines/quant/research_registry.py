"""
Research registry — additive registration of the certified analytical surface.

Phase 5.1 — Certified Analytical Compute Surface (WP-1).

This module wires the research backends (Python reference + optional C++ candidate)
into the existing ``BackendRouter`` using the frozen registration API.  It is
strictly additive:

    * ``create_research_router()`` — a ``BackendRouter`` with the Python
      reference backend and an optional C++ research candidate registered.
    * ``register_research_backend()`` — register a research backend as a
      candidate on an existing router.
    * ``create_research_engine()`` — a ``ResearchEngine`` over a research
      backend (Python reference by default; C++ candidate opt-in).

The C++ candidate is optional. If the compiled module is not available, the
registry silently uses the Python reference. The parity test
(``researchos/engines/quant/parity_test.py``) enforces that any available
C++ engine produces bit-exact results.

This is a certification/trust layer only — it computes no trading decisions.
"""

from __future__ import annotations

from researchos.engines.quant.backend import PythonQuantBackend
from researchos.engines.quant.interface import QuantComputationInterface
from researchos.engines.quant.research_engine import PythonResearchBackend, ResearchEngine
from researchos.engines.quant.research_interface import RESEARCH_OPERATIONS, ResearchComputationInterface
from researchos.engines.quant.router import BackendRouter


def _get_cpp_backend() -> QuantComputationInterface | None:
    """Attempt to load the C++ research backend. Return None if unavailable."""
    try:
        from researchos.engines.quant.cpp_quant import run_ml_backtest_cpp  # noqa: F401

        # The C++ module is available but only implements run_ml_backtest_cpp.
        # It does not implement the full QuantComputationInterface, so we
        # cannot use it as a drop-in replacement yet.
        # Return None until a full C++ interface is implemented.
        return None
    except (ImportError, ModuleNotFoundError, OSError):
        return None


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
        the C++ research candidate.
    """
    reference = reference_backend or PythonQuantBackend()
    router = BackendRouter(reference_backend=reference)
    if register_cpp:
        cpp_backend = _get_cpp_backend()
        if cpp_backend is not None:
            register_research_backend(router, cpp_backend)
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
            C++ research candidate if available.

    Returns:
        A ``ResearchEngine`` facade.
    """
    if backend is not None:
        return ResearchEngine(backend=backend)
    if use_cpp:
        cpp_backend = _get_cpp_backend()
        if cpp_backend is not None:
            return ResearchEngine(backend=PythonResearchBackend())
    return ResearchEngine(backend=PythonResearchBackend())


__all__ = [
    "RESEARCH_OPERATIONS",
    "register_research_backend",
    "create_research_router",
    "create_research_engine",
]
