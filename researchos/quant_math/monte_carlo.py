from __future__ import annotations

import math
import random
from collections.abc import Sequence

from researchos.quant_math.contracts import MonteCarloMeasurement


def simulate_terminal_distribution(
    prices: Sequence[float], simulations: int = 1000, seed: int = 42
) -> MonteCarloMeasurement:
    p = [float(x) for x in prices]
    if len(p) < 2:
        raise ValueError("Monte Carlo requires at least two prices")
    if any(not math.isfinite(x) or x <= 0 for x in p):
        raise ValueError("prices must be finite and positive")
    if simulations <= 0:
        raise ValueError("simulations must be positive")
    returns = [p[i] / p[i - 1] - 1.0 for i in range(1, len(p))]
    rng = random.Random(seed)
    out = []
    for _ in range(simulations):
        value = p[0]
        for _ in returns:
            value *= 1.0 + rng.choice(returns)
        out.append(value)
    out.sort()

    def pct(q: float) -> float:
        pos = q * (len(out) - 1)
        lo, hi = math.floor(pos), math.ceil(pos)
        return out[lo] if lo == hi else out[lo] + (out[hi] - out[lo]) * (pos - lo)

    m = sum(out) / len(out)
    sd = math.sqrt(sum((x - m) ** 2 for x in out) / len(out))
    return MonteCarloMeasurement(
        simulations, seed, m, sd, pct(0.05), pct(0.50), pct(0.95)
    )
