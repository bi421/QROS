"""Python facade for the compiled constraint-first probability kernel."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray


def evaluate_candidates(
    closes: ArrayLike,
    target_bps: ArrayLike,
    horizons: ArrayLike,
    directions: ArrayLike,
    *,
    max_unique_horizons: int = 64,
) -> dict[str, Any]:
    """Estimate historical forward-return hit rates using the native C++ kernel."""
    close_array: NDArray[np.float64] = np.ascontiguousarray(closes, dtype=np.float64)
    target_array: NDArray[np.float64] = np.ascontiguousarray(target_bps, dtype=np.float64)
    horizon_array: NDArray[np.int32] = np.ascontiguousarray(horizons, dtype=np.int32)
    direction_array: NDArray[np.int32] = np.ascontiguousarray(directions, dtype=np.int32)

    try:
        from cpp_quant_engine import qros_constraint_engine
    except ImportError as exc:
        raise ImportError(
            "QROS constraint-first C++ extension is not built. "
            "Build/install QROS with pip install -e . using CMake and nanobind."
        ) from exc

    return qros_constraint_engine.evaluate_candidates(
        close_array,
        target_array,
        horizon_array,
        direction_array,
        max_unique_horizons,
    )


__all__ = ["evaluate_candidates"]
