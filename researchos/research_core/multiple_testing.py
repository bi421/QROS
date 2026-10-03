"""Deterministic multiple-testing correction primitives for research evidence.

These functions adjust p-values only; they do not decide whether a research
claim is true or whether an edge is economically useful. Governance layers
must consume the adjusted values together with OOS, replication, calibration,
and evidence gates.
"""

from __future__ import annotations

from dataclasses import dataclass


MULTIPLE_TESTING_SCHEMA_VERSION = "multiple-testing.v1"


@dataclass(frozen=True)
class MultipleTestingResult:
    """Immutable adjusted-p-value result preserving original ordering."""

    schema_version: str
    method: str
    p_values: tuple[float, ...]
    adjusted_p_values: tuple[float, ...]
    alpha: float

    def __post_init__(self) -> None:
        if self.schema_version != MULTIPLE_TESTING_SCHEMA_VERSION:
            raise ValueError("unsupported multiple-testing schema version")
        if self.method not in {"holm", "benjamini_hochberg"}:
            raise ValueError("unsupported multiple-testing method")
        if len(self.p_values) != len(self.adjusted_p_values):
            raise ValueError("p-value lengths must match")
        if not 0.0 < self.alpha < 1.0:
            raise ValueError("alpha must be in (0, 1)")
        if any(not 0.0 <= p <= 1.0 for p in self.p_values):
            raise ValueError("p_values must be in [0, 1]")
        if any(not 0.0 <= p <= 1.0 for p in self.adjusted_p_values):
            raise ValueError("adjusted_p_values must be in [0, 1]")

    def reject(self) -> tuple[bool, ...]:
        """Return per-hypothesis rejection decisions at the declared alpha."""
        return tuple(p <= self.alpha for p in self.adjusted_p_values)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "method": self.method,
            "p_values": list(self.p_values),
            "adjusted_p_values": list(self.adjusted_p_values),
            "alpha": self.alpha,
            "reject": list(self.reject()),
        }


def adjust_p_values(
    p_values: tuple[float, ...] | list[float],
    *,
    method: str,
    alpha: float = 0.05,
) -> MultipleTestingResult:
    """Apply a deterministic Holm or Benjamini-Hochberg correction."""
    values = tuple(float(p) for p in p_values)
    if method == "holm":
        adjusted = _holm(values)
    elif method == "benjamini_hochberg":
        adjusted = _benjamini_hochberg(values)
    else:
        raise ValueError("unsupported multiple-testing method")
    return MultipleTestingResult(
        schema_version=MULTIPLE_TESTING_SCHEMA_VERSION,
        method=method,
        p_values=values,
        adjusted_p_values=adjusted,
        alpha=alpha,
    )


def _holm(values: tuple[float, ...]) -> tuple[float, ...]:
    n = len(values)
    if n == 0:
        return ()
    order = sorted(range(n), key=lambda index: (values[index], index))
    adjusted = [0.0] * n
    running = 0.0
    for rank, index in enumerate(order):
        candidate = min(1.0, (n - rank) * values[index])
        running = max(running, candidate)
        adjusted[index] = running
    return tuple(adjusted)


def _benjamini_hochberg(values: tuple[float, ...]) -> tuple[float, ...]:
    n = len(values)
    if n == 0:
        return ()
    order = sorted(range(n), key=lambda index: (values[index], index))
    adjusted = [0.0] * n
    running = 1.0
    for rank in range(n - 1, -1, -1):
        index = order[rank]
        candidate = min(1.0, values[index] * n / (rank + 1))
        running = min(running, candidate)
        adjusted[index] = running
    return tuple(adjusted)
