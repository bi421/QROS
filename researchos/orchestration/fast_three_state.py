"""Minimal close-only three-state XAUUSD classifier.

Hot path returns exactly one integer: +1 (up), -1 (down), or 0 (range /
insufficient warm-up). No pandas, NumPy, model, I/O, probabilities, or reports.
This is a fast baseline classifier, not a validated trading signal.
"""
from __future__ import annotations

import math
from collections import deque


class FastThreeState:
    """O(1) incremental close-only classifier with bounded rolling memory."""

    __slots__ = (
        "lookback", "efficiency_threshold", "min_move_bps",
        "_closes", "_abs_returns", "_path", "_last_close",
    )

    def __init__(
        self,
        lookback: int = 32,
        efficiency_threshold: float = 0.35,
        min_move_bps: float = 5.0,
    ) -> None:
        if lookback < 2:
            raise ValueError("lookback must be >= 2")
        if not math.isfinite(efficiency_threshold) or not 0.0 <= efficiency_threshold <= 1.0:
            raise ValueError("efficiency_threshold must be finite and in [0, 1]")
        if not math.isfinite(min_move_bps) or min_move_bps < 0.0:
            raise ValueError("min_move_bps must be finite and >= 0")
        self.lookback = lookback
        self.efficiency_threshold = efficiency_threshold
        self.min_move_bps = min_move_bps
        self._closes: deque[float] = deque()
        self._abs_returns: deque[float] = deque()
        self._path = 0.0
        self._last_close: float | None = None

    def update(self, close: float) -> int:
        """Consume one completed candle close; return only -1, 0, or +1."""
        close = float(close)
        if not math.isfinite(close) or close <= 0.0:
            raise ValueError("close must be finite and positive")

        previous = self._last_close
        if previous is not None:
            step = abs(close - previous)
            if len(self._closes) >= self.lookback:
                self._closes.popleft()
                expired = self._abs_returns.popleft()
                self._path -= expired
            self._closes.append(close)
            self._abs_returns.append(step)
            self._path += step
        else:
            self._closes.append(close)
        self._last_close = close

        if len(self._closes) < self.lookback:
            return 0

        net = close - self._closes[0]
        if self._path <= 0.0:
            return 0
        efficiency = abs(net) / self._path
        move_bps = abs(net) / close * 10_000.0
        if efficiency < self.efficiency_threshold or move_bps < self.min_move_bps:
            return 0
        return 1 if net > 0.0 else -1 if net < 0.0 else 0


__all__ = ["FastThreeState"]
