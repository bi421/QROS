from __future__ import annotations

from collections.abc import Sequence

from researchos.quant_math.matrix import euclidean_distance_vector

MULTIVARIATE_VERSION = "MULTIVARIATE_V1"


def normalize_minmax(
    rows: Sequence[Sequence[float]],
) -> tuple[tuple[float, ...], ...]:
    if not rows:
        raise ValueError("rows must not be empty")
    data = [tuple(float(x) for x in row) for row in rows]
    width = len(data[0])
    if width == 0 or any(len(row) != width for row in data):
        raise ValueError("rows must be rectangular")
    mins = [min(row[j] for row in data) for j in range(width)]
    spans = [max(row[j] for row in data) - mins[j] for j in range(width)]
    spans = [s if s else 1.0 for s in spans]
    return tuple(
        tuple((row[j] - mins[j]) / spans[j] for j in range(width))
        for row in data
    )


def nearest_neighbors(
    query: Sequence[float], rows: Sequence[Sequence[float]], k: int = 5
) -> list[tuple[int, float]]:
    if k <= 0:
        raise ValueError("k must be positive")
    q = tuple(float(x) for x in query)
    distances = [
        (i, euclidean_distance_vector(q, row)) for i, row in enumerate(rows)
    ]
    return sorted(distances, key=lambda item: (item[1], item[0]))[:k]
