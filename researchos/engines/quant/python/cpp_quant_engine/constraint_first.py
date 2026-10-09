"""Python facade for the compiled constraint-first probability kernel."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray


def _strict_int32_array(values: ArrayLike, name: str, *, positive: bool = False,
                        direction: bool = False) -> NDArray[np.int32]:
    """Validate integer-valued inputs before narrowing them to int32."""
    array = np.asarray(values)
    if array.ndim != 1:
        raise ValueError(f"{name} must be a one-dimensional array")
    if not (
        np.issubdtype(array.dtype, np.integer)
        or np.issubdtype(array.dtype, np.floating)
    ):
        raise ValueError(f"{name} must contain integer-valued numbers")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")
    if not np.equal(array, np.trunc(array)).all():
        raise ValueError(f"{name} must contain integer-valued numbers")
    limits = np.iinfo(np.int32)
    if (array < limits.min).any() or (array > limits.max).any():
        raise ValueError(f"{name} values must fit in int32")
    if positive and (array <= 0).any():
        raise ValueError(f"{name} values must be positive")
    if direction and not np.isin(array, (-1, 1)).all():
        raise ValueError("direction values must be -1 or 1")
    return np.ascontiguousarray(array, dtype=np.int32)


def evaluate_candidates(
    closes: ArrayLike,
    target_bps: ArrayLike,
    horizons: ArrayLike,
    directions: ArrayLike,
    *,
    max_unique_horizons: int = 64,
    minimum_probability: float = 0.0,
    minimum_samples: int = 1,
) -> dict[str, Any]:
    """Estimate historical forward-return hit rates using the native C++ kernel."""
    close_array: NDArray[np.float64] = np.ascontiguousarray(closes, dtype=np.float64)
    target_array: NDArray[np.float64] = np.ascontiguousarray(target_bps, dtype=np.float64)
    horizon_array = _strict_int32_array(horizons, "horizon", positive=True)
    direction_array = _strict_int32_array(directions, "direction", direction=True)

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
        minimum_probability,
        minimum_samples,
    )


__all__ = ["evaluate_candidates"]
