"""Bounded-memory incremental XAUUSD market-regime updates.

Each candle updates fixed-size rolling state; historical data is not rescanned.
Hurst is refreshed periodically as a diagnostic and does not drive the label.
"""

from __future__ import annotations

import math
from collections import deque

import numpy as np

from researchos.orchestration.xauusd_regime_detection import STATES, _hurst_variance_time


class IncrementalRegimeEngine:
    """Incrementally classify completed OHLC candles with O(1) rolling updates."""

    def __init__(
        self,
        *,
        lookback: int = 100,
        adx_period: int = 14,
        range_adx: float = 20.0,
        trend_adx: float = 25.0,
        slope_floor: float = 0.05,
        dirichlet_alpha: float = 1.0,
        hurst_refresh_every: int = 10,
    ) -> None:
        if lookback < 40 or adx_period < 2:
            raise ValueError("lookback must be >= 40 and adx_period >= 2")
        if not (0 <= range_adx < trend_adx) or slope_floor < 0:
            raise ValueError("invalid regime thresholds")
        if not math.isfinite(dirichlet_alpha) or dirichlet_alpha <= 0:
            raise ValueError("dirichlet_alpha must be finite and positive")
        if hurst_refresh_every < 1:
            raise ValueError("hurst_refresh_every must be >= 1")

        self.lookback = lookback
        self.adx_period = adx_period
        self.range_adx = range_adx
        self.trend_adx = trend_adx
        self.slope_floor = slope_floor
        self.alpha = dirichlet_alpha
        self.hurst_refresh_every = hurst_refresh_every
        self.count = 0
        self.previous_high: float | None = None
        self.previous_low: float | None = None
        self.previous_close: float | None = None
        self.log_closes: deque[float] = deque(maxlen=lookback)
        self.log_returns: deque[float] = deque(maxlen=lookback - 1)
        self.return_sum = 0.0
        self.return_sq_sum = 0.0
        self.log_sum = 0.0
        self.log_xy_sum = 0.0
        self.true_ranges: deque[float] = deque(maxlen=adx_period)
        self.plus_dms: deque[float] = deque(maxlen=adx_period)
        self.minus_dms: deque[float] = deque(maxlen=adx_period)
        self.dx_values: deque[float] = deque(maxlen=adx_period)
        self.hurst: float | None = None
        self.last_state: str | None = None
        self.transition_counts = {
            state: {next_state: self.alpha for next_state in STATES} for state in STATES
        }
        self.transition_count = 0

    @staticmethod
    def _append_rolling(values: deque[float], value: float) -> float | None:
        """Append to a bounded queue and return the evicted value, if any."""
        evicted = values[0] if len(values) == values.maxlen else None
        values.append(value)
        return evicted

    def update(self, high: float, low: float, close: float) -> dict[str, object] | None:
        """Consume one completed candle. Return None until warm-up is complete."""
        high, low, close = float(high), float(low), float(close)
        if not all(math.isfinite(v) and v > 0 for v in (high, low, close)):
            raise ValueError("OHLC values must be finite and positive")
        if high < max(low, close) or low > min(high, close):
            raise ValueError("invalid OHLC candle geometry")

        old_close = self.previous_close
        old_high = self.previous_high
        old_low = self.previous_low
        log_close = math.log(close)

        if old_close is not None:
            log_return = log_close - math.log(old_close)
            evicted_return = self._append_rolling(self.log_returns, log_return)
            if evicted_return is not None:
                self.return_sum -= evicted_return
                self.return_sq_sum -= evicted_return * evicted_return
            self.return_sum += log_return
            self.return_sq_sum += log_return * log_return

        if len(self.log_closes) == self.lookback:
            evicted_log = self.log_closes.popleft()
            self.log_xy_sum -= self.log_sum - evicted_log
            self.log_sum -= evicted_log
        x_index = len(self.log_closes)
        self.log_closes.append(log_close)
        self.log_sum += log_close
        self.log_xy_sum += x_index * log_close

        tr = high - low
        plus_dm = 0.0
        minus_dm = 0.0
        if old_close is not None:
            tr = max(tr, abs(high - old_close), abs(low - old_close))
        if old_high is not None and old_low is not None:
            up_move = high - old_high
            down_move = old_low - low
            plus_dm = up_move if up_move > down_move and up_move > 0 else 0.0
            minus_dm = down_move if down_move > up_move and down_move > 0 else 0.0
        self._append_rolling(self.true_ranges, tr)
        self._append_rolling(self.plus_dms, plus_dm)
        self._append_rolling(self.minus_dms, minus_dm)

        adx = plus_di = minus_di = None
        if len(self.true_ranges) == self.adx_period:
            tr_sum = sum(self.true_ranges)
            plus_sum = sum(self.plus_dms)
            minus_sum = sum(self.minus_dms)
            if tr_sum > 0:
                plus_di = 100.0 * plus_sum / tr_sum
                minus_di = 100.0 * minus_sum / tr_sum
                denom = plus_di + minus_di
                dx = 100.0 * abs(plus_di - minus_di) / denom if denom > 0 else math.nan
                self._append_rolling(self.dx_values, dx)
                if len(self.dx_values) == self.adx_period and all(
                    math.isfinite(value) for value in self.dx_values
                ):
                    adx = sum(self.dx_values) / self.adx_period
            else:
                self._append_rolling(self.dx_values, math.nan)

        self.count += 1
        if self.count % self.hurst_refresh_every == 0 and len(self.log_closes) >= 40:
            self.hurst = _hurst_variance_time(np.asarray(self.log_closes, dtype=float))

        self.previous_high, self.previous_low, self.previous_close = high, low, close
        if (
            len(self.log_closes) < self.lookback
            or self.count < self.adx_period * 2 + 1
            or adx is None
            or plus_di is None
            or minus_di is None
        ):
            return None

        n = len(self.log_closes)
        sum_x = n * (n - 1) / 2.0
        sum_xx = n * (n - 1) * (2 * n - 1) / 6.0
        denominator = n * sum_xx - sum_x * sum_x
        slope = (n * self.log_xy_sum - sum_x * self.log_sum) / denominator
        return_mean = self.return_sum / max(len(self.log_returns), 1)
        return_variance = max(
            self.return_sq_sum / max(len(self.log_returns), 1) - return_mean * return_mean,
            0.0,
        )
        return_scale = math.sqrt(return_variance)
        normalized_slope = slope / return_scale if return_scale > 0 else 0.0

        if adx >= self.trend_adx and normalized_slope > self.slope_floor and plus_di > minus_di:
            state = "UP"
        elif adx >= self.trend_adx and normalized_slope < -self.slope_floor and minus_di > plus_di:
            state = "DOWN"
        else:
            state = "RANGE"

        if self.last_state in STATES:
            self.transition_counts[self.last_state][state] += 1.0
            self.transition_count += 1
        self.last_state = state
        row = self.transition_counts[state]
        total = sum(row.values())
        probabilities = {key: row[key] / total for key in STATES}
        return {
            "status": "CLASSIFIED",
            "instrument": "XAUUSD",
            "bar_count_seen": self.count,
            "current_state": state,
            "features": {
                "adx": adx,
                "plus_di": plus_di,
                "minus_di": minus_di,
                "normalized_log_price_slope": normalized_slope,
                "hurst_variance_time": self.hurst,
            },
            "state_probabilities_next": probabilities,
            "probability_status": "SMOOTHED_ONLINE_STATE_TRANSITION_FREQUENCY_NOT_CALIBRATED",
            "historical_transition_count": self.transition_count,
            "execution_enabled": False,
        }


__all__ = ["IncrementalRegimeEngine"]
