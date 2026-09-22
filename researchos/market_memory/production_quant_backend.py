"""Production quantitative backend boundary for Market Memory evidence.

This module keeps event extraction/statistical methodology in Market Memory while
making the numerical backend used by the real-data production report explicit.
The C++ backend is never accepted silently: when ``require_cpp`` is true, any
fallback to Python is treated as a production execution failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from researchos.quant_engine.cpp_backend import CppQuantAdapter
from researchos.quant_engine.router import BackendRouter


@dataclass(frozen=True)
class ProductionQuantBackendAudit:
    """Immutable audit record proving which numerical backend produced output."""

    returns: dict[str, Any]
    statistics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "returns": dict(self.returns),
            "statistics": dict(self.statistics),
        }


def _metadata_dict(metadata: Any) -> dict[str, Any]:
    value = metadata.to_dict()
    return {
        "operation": value["operation"],
        "backend": value["backend"],
        "version": value["version"],
        "fallback_used": bool(value["fallback_used"]),
        "validation_status": value["validation_status"],
        "result_hash": value["result_hash"],
        "error_code": value["error_code"],
        "attempted_backends": list(value.get("attempted_backends", [])),
    }


def run_production_quant_backend_audit(
    closes: list[float],
    *,
    require_cpp: bool = True,
) -> ProductionQuantBackendAudit:
    """Execute certified numerical operations through the production router.

    The first operation computes daily percentage returns from the real XAUUSD
    close series. The second computes descriptive statistics from those exact
    backend-produced returns. Both operations are validated by ``BackendRouter``
    against the Python reference backend.

    When ``require_cpp`` is true, the production boundary fails closed unless
    the returned result was actually produced by ``CppQuantAdapter`` without
    fallback.
    """
    if len(closes) < 2:
        raise ValueError("Production quant backend audit requires at least 2 closes")

    adapter = CppQuantAdapter()
    if require_cpp and not adapter.is_cpp:
        raise RuntimeError(
            "C++ Quant Engine is unavailable. Production evidence requires an active C++ backend."
        )

    router = BackendRouter(candidates=[adapter])

    returns_result = router.execute(
        "calculate_returns",
        {"prices": list(closes), "return_type": "percentage"},
    )
    returns_metadata = _metadata_dict(returns_result.metadata)

    statistics_result = router.execute(
        "calculate_statistics",
        {"returns": list(returns_result.output)},
    )
    statistics_metadata = _metadata_dict(statistics_result.metadata)

    if require_cpp:
        for metadata in (returns_metadata, statistics_metadata):
            if (
                metadata["backend"] != "CppQuantAdapter"
                or metadata["fallback_used"]
                or metadata["validation_status"] != "passed"
                or metadata["error_code"] != "ok"
            ):
                raise RuntimeError(
                    "Production C++ trust-boundary check failed: "
                    f"{metadata}"
                )

    statistics = dict(statistics_result.output)
    mean_value = statistics.get("mean", 0.0)
    stddev_value = statistics.get("stddev", statistics.get("std", 0.0))
    if mean_value is None or stddev_value is None:
        raise RuntimeError("Production statistics backend returned incomplete numeric metadata")
    return ProductionQuantBackendAudit(
        returns={
            **returns_metadata,
            "count": len(returns_result.output),
        },
        statistics={
            **statistics_metadata,
            "count": int(statistics.get("count", len(returns_result.output))),
            "mean": float(mean_value),
            "stddev": float(stddev_value),
        },
    )


__all__ = ["ProductionQuantBackendAudit", "run_production_quant_backend_audit"]
