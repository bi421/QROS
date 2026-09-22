from __future__ import annotations

import math
from dataclasses import dataclass
from collections.abc import Callable, Sequence

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _rolling_apply(
    values: Sequence[float | None],
    period: int,
    fn: Callable[[list[float]], float],
) -> list[float | None]:
    """Apply fn to each trailing window of `period` values. None while the
    window is shorter than `period` or contains a None."""
    n = len(values)
    out: list[float | None] = [None] * n
    for i in range(period - 1, n):
        window = list(values[i - period + 1 : i + 1])
        numeric_window = [v for v in window if v is not None]
        if len(numeric_window) != period:
            continue
        out[i] = fn(numeric_window)
    return out


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _pstd(xs: list[float]) -> float:
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


# ---------------------------------------------------------------------------
# returns
# ---------------------------------------------------------------------------


def returns(prices: Sequence[float]) -> list[float | None]:
    prices = list(prices)
    out: list[float | None] = [None] * len(prices)
    for i in range(1, len(prices)):
        prev = prices[i - 1]
        out[i] = (prices[i] - prev) / prev if prev != 0 else None
    return out


def log_returns(prices: Sequence[float]) -> list[float | None]:
    prices = list(prices)
    out: list[float | None] = [None] * len(prices)
    for i in range(1, len(prices)):
        prev = prices[i - 1]
        if prev != 0 and prices[i] > 0 and prev > 0:
            out[i] = math.log(prices[i] / prev)
    return out


# kept for backward compatibility with earlier callers
def returns_feature(prices: Sequence[float]) -> list[float]:
    prices = list(prices)
    if len(prices) < 2:
        return []
    return [(prices[i] - prices[i - 1]) / prices[i - 1] if prices[i - 1] != 0 else 0.0 for i in range(1, len(prices))]


# ---------------------------------------------------------------------------
# rolling stats
# ---------------------------------------------------------------------------


def rolling_mean(prices: Sequence[float], period: int) -> list[float | None]:
    prices = list(prices)
    return _rolling_apply(prices, period, _mean)


def rolling_std(prices: Sequence[float], period: int) -> list[float | None]:
    prices = list(prices)
    return _rolling_apply(prices, period, _pstd)


def rolling_volatility(prices: Sequence[float], period: int) -> list[float | None]:
    rets = returns(prices)
    return _rolling_apply(rets, period, _pstd)


# ---------------------------------------------------------------------------
# price / momentum features
# ---------------------------------------------------------------------------


def momentum(prices, period: int) -> list[float | None]:
    prices = list(prices)
    out: list[float | None] = [None] * len(prices)
    for i in range(period, len(prices)):
        out[i] = prices[i] - prices[i - period]
    return out


def rate_of_change(prices, period: int) -> list[float | None]:
    prices = list(prices)
    out: list[float | None] = [None] * len(prices)
    for i in range(period, len(prices)):
        base = prices[i - period]
        out[i] = (prices[i] - base) / base if base != 0 else None
    return out


# alternate implementation name required by the tests; same contract as
# rate_of_change (kept separate in case the two diverge later)
def roc_feature(prices, period: int = 14) -> list[float | None]:
    return rate_of_change(prices, period)


def price_distance_from_ma(prices, period: int) -> list[float | None]:
    prices = list(prices)
    ma = rolling_mean(prices, period)
    out: list[float | None] = [None] * len(prices)
    for i in range(len(prices)):
        if ma[i] is not None and ma[i] != 0:
            out[i] = (prices[i] - ma[i]) / ma[i]
    return out


# raw price pass-through feature (identity), kept for older callers that
# expect a "price_feature" column alongside the derived ones
def price_feature(prices) -> list[float]:
    return [float(p) for p in prices]


# ---------------------------------------------------------------------------
# classic technical indicators
# ---------------------------------------------------------------------------


def rsi_feature(prices, period: int = 14) -> list[float | None]:
    prices = list(prices)
    n = len(prices)
    gains: list[float | None] = [None] * n
    losses: list[float | None] = [None] * n
    for i in range(1, n):
        diff = prices[i] - prices[i - 1]
        gains[i] = max(diff, 0.0)
        losses[i] = max(-diff, 0.0)

    out: list[float | None] = [None] * n
    for i in range(period, n):
        g_window = gains[i - period + 1 : i + 1]
        l_window = losses[i - period + 1 : i + 1]
        numeric_gains = [v for v in g_window if v is not None]
        numeric_losses = [v for v in l_window if v is not None]
        if len(numeric_gains) != period or len(numeric_losses) != period:
            continue
        avg_gain = _mean(numeric_gains)
        avg_loss = _mean(numeric_losses)
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def ema_feature(prices, period: int = 14) -> list[float]:
    prices = list(prices)
    if not prices:
        return []
    multiplier = 2.0 / (period + 1)
    out = [prices[0]]
    for price in prices[1:]:
        out.append((price - out[-1]) * multiplier + out[-1])
    return out


def sma_feature(prices, period: int = 14) -> list[float]:
    prices = list(prices)
    if len(prices) < period:
        return []
    return [sum(prices[i - period + 1 : i + 1]) / period for i in range(period - 1, len(prices))]


def macd_feature(prices, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, list[float]]:
    prices = list(prices)
    fast_ema = ema_feature(prices, fast)
    slow_ema = ema_feature(prices, slow)
    macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
    signal_line = ema_feature(macd_line, signal)
    hist = [m - s for m, s in zip(macd_line, signal_line)]
    return {
        "macd": macd_line,
        "macd_signal": signal_line,
        "macd_hist": hist,
    }


def atr_feature(high, low, close, period: int = 14) -> list[float | None]:
    high, low, close = list(high), list(low), list(close)
    n = len(close)
    tr: list[float | None] = [None] * n
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
    return _rolling_apply(tr, period, _mean)


def bollinger_feature(prices, period: int = 20, std_factor: float = 2.0) -> dict[str, list[float | None]]:
    prices = list(prices)
    mid = rolling_mean(prices, period)
    std = rolling_std(prices, period)
    n = len(prices)
    upper: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n
    pct_b: list[float | None] = [None] * n
    for i in range(n):
        mid_value = mid[i]
        std_value = std[i]
        if mid_value is None or std_value is None:
            continue
        upper_value = mid_value + std_factor * std_value
        lower_value = mid_value - std_factor * std_value
        upper[i] = upper_value
        lower[i] = lower_value
        band = upper_value - lower_value
        pct_b[i] = (prices[i] - lower_value) / band if band != 0 else None
    return {
        "bb_upper": upper,
        "bb_middle": mid,
        "bb_lower": lower,
        "bb_pct_b": pct_b,
    }


def stochastic_feature(high, low, close, period: int = 14, smooth: int = 3) -> dict[str, list[float | None]]:
    high, low, close = list(high), list(low), list(close)
    n = len(close)
    k: list[float | None] = [None] * n
    for i in range(period - 1, n):
        hh = max(high[i - period + 1 : i + 1])
        ll = min(low[i - period + 1 : i + 1])
        rng = hh - ll
        k[i] = 100.0 * (close[i] - ll) / rng if rng != 0 else 0.0
    d = _rolling_apply(k, smooth, _mean)
    return {"stoch_k": k, "stoch_d": d}


def cci_feature(high, low, close, period: int = 20) -> list[float | None]:
    high, low, close = list(high), list(low), list(close)
    n = len(close)
    tp = [(high[i] + low[i] + close[i]) / 3.0 for i in range(n)]
    sma_tp = rolling_mean(tp, period)
    out: list[float | None] = [None] * n
    for i in range(period - 1, n):
        sma_value = sma_tp[i]
        if sma_value is None:
            continue
        window = tp[i - period + 1 : i + 1]
        mean_dev = _mean([abs(x - sma_value) for x in window])
        out[i] = (tp[i] - sma_value) / (0.015 * mean_dev) if mean_dev != 0 else 0.0
    return out


def mfi_feature(high, low, close, volume, period: int = 14) -> list[float | None]:
    high, low, close, volume = list(high), list(low), list(close), list(volume)
    n = len(close)
    tp = [(high[i] + low[i] + close[i]) / 3.0 for i in range(n)]
    raw_money_flow = [tp[i] * volume[i] for i in range(n)]

    pos_flow: list[float] = [0.0] * n
    neg_flow: list[float] = [0.0] * n
    for i in range(1, n):
        if tp[i] > tp[i - 1]:
            pos_flow[i] = raw_money_flow[i]
        elif tp[i] < tp[i - 1]:
            neg_flow[i] = raw_money_flow[i]

    out: list[float | None] = [None] * n
    for i in range(period, n):
        pos_sum = sum(pos_flow[i - period + 1 : i + 1])
        neg_sum = sum(neg_flow[i - period + 1 : i + 1])
        if neg_sum == 0:
            out[i] = 100.0
        else:
            mfr = pos_sum / neg_sum
            out[i] = 100.0 - (100.0 / (1.0 + mfr))
    return out


def vwap_feature(high, low, close, volume) -> list[float | None]:
    high, low, close, volume = list(high), list(low), list(close), list(volume)
    n = len(close)
    out: list[float | None] = [None] * n
    cum_pv = 0.0
    cum_v = 0.0
    for i in range(n):
        tp = (high[i] + low[i] + close[i]) / 3.0
        cum_pv += tp * volume[i]
        cum_v += volume[i]
        out[i] = cum_pv / cum_v if cum_v != 0 else None
    return out


# kept for backward compatibility with earlier callers
def volatility_feature(prices, period: int = 14) -> list[float]:
    rets = returns_feature(prices)
    if len(rets) < period:
        return []
    result = []
    for i in range(period - 1, len(rets)):
        window = rets[i - period + 1 : i + 1]
        mean = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        result.append(math.sqrt(variance))
    return result


# ---------------------------------------------------------------------------
# volatility features
# ---------------------------------------------------------------------------


def historical_volatility(prices, period: int = 20) -> list[float | None]:
    lr = log_returns(prices)
    return _rolling_apply(lr, period, _pstd)


def volatility_ratio(prices, short_period: int = 10, long_period: int = 30) -> list[float | None]:
    short_vol = rolling_volatility(prices, short_period)
    long_vol = rolling_volatility(prices, long_period)
    n = len(short_vol)
    out: list[float | None] = [None] * n
    for i in range(n):
        short_value = short_vol[i]
        long_value = long_vol[i]
        if short_value is None or long_value is None or long_value == 0:
            continue
        out[i] = short_value / long_value
    return out


def volatility_percentile(prices, period: int = 20, lookback: int = 60) -> list[float | None]:
    vol = rolling_volatility(prices, period)
    n = len(vol)
    out: list[float | None] = [None] * n
    for i in range(n):
        vol_value = vol[i]
        if vol_value is None:
            continue
        start = max(0, i - lookback + 1)
        window = [v for v in vol[start : i + 1] if v is not None]
        if not window:
            continue
        rank = sum(1 for v in window if v <= vol_value)
        out[i] = rank / len(window)
    return out


def rolling_drawdown(prices, period: int = 20) -> list[float | None]:
    prices = list(prices)
    n = len(prices)
    out: list[float | None] = [None] * n
    for i in range(period - 1, n):
        window = prices[i - period + 1 : i + 1]
        peak = max(window)
        out[i] = (prices[i] - peak) / peak if peak != 0 else 0.0
    return out


# ---------------------------------------------------------------------------
# market regime features
# ---------------------------------------------------------------------------


def trend_state(prices, short_period: int = 20, long_period: int = 50) -> list[float | None]:
    short_ma = rolling_mean(prices, short_period)
    long_ma = rolling_mean(prices, long_period)
    n = len(prices)
    out: list[float | None] = [None] * n
    for i in range(n):
        short_value = short_ma[i]
        long_value = long_ma[i]
        if short_value is None or long_value is None:
            continue
        if short_value > long_value:
            out[i] = 1.0
        elif short_value < long_value:
            out[i] = -1.0
        else:
            out[i] = 0.0
    return out


def volatility_regime(prices, short_period: int = 20, long_period: int = 60) -> list[float | None]:
    short_vol = historical_volatility(prices, short_period)
    long_vol = historical_volatility(prices, long_period)
    n = len(prices)
    out: list[float | None] = [None] * n
    for i in range(n):
        short_value = short_vol[i]
        long_value = long_vol[i]
        if short_value is None or long_value is None:
            continue
        if short_value > long_value:
            out[i] = 1.0
        elif short_value < long_value:
            out[i] = -1.0
        else:
            out[i] = 0.0
    return out


def momentum_regime(prices, period: int = 14) -> list[float | None]:
    mom = momentum(prices, period)
    out: list[float | None] = [None] * len(mom)
    for i, v in enumerate(mom):
        if v is None:
            continue
        out[i] = 1.0 if v > 0 else (-1.0 if v < 0 else 0.0)
    return out


# ---------------------------------------------------------------------------
# feature builder
# ---------------------------------------------------------------------------


@dataclass
class FeatureSet:
    feature_names: list[str]
    data: list[list[float | None]]
    n_features: int
    n_observations: int
    labels: list[float] | None = None


@dataclass
class FeatureBuilder:
    close: list[float]
    high: list[float]
    low: list[float]
    volume: list[float]
    labels: list[float] | None = None

    def build(self, drop_na: bool = False) -> FeatureSet:
        close, high, low, volume = self.close, self.high, self.low, self.volume
        n = len(close)

        columns: dict[str, list[float | None]] = {}
        columns["returns"] = returns(close)
        columns["log_returns"] = log_returns(close)
        columns["rolling_mean_20"] = rolling_mean(close, 20)
        columns["rolling_std_20"] = rolling_std(close, 20)
        columns["momentum_14"] = momentum(close, 14)
        columns["rate_of_change_14"] = rate_of_change(close, 14)
        columns["rsi_14"] = rsi_feature(close, 14)

        macd = macd_feature(close)
        columns["macd_hist"] = macd["macd_hist"]

        columns["atr_14"] = atr_feature(high, low, close, 14)

        bb = bollinger_feature(close, 20)
        columns["bb_pct_b"] = bb["bb_pct_b"]

        stoch = stochastic_feature(high, low, close, 14, 3)
        columns["stoch_k"] = stoch["stoch_k"]

        columns["cci_20"] = cci_feature(high, low, close, 20)
        columns["mfi_14"] = mfi_feature(high, low, close, volume, 14)
        columns["vwap"] = vwap_feature(high, low, close, volume)
        columns["hist_vol_20"] = historical_volatility(close, 20)
        columns["vol_ratio"] = volatility_ratio(close, 10, 30)
        columns["trend_state"] = trend_state(close, 20, 50)
        columns["vol_regime"] = volatility_regime(close, 20, 60)
        columns["momentum_regime"] = momentum_regime(close, 14)

        feature_names = list(columns.keys())
        rows: list[list[float | None]] = []
        labels = self.labels
        labels_out: list[float] | None = [] if labels is not None else None

        for i in range(n):
            row = [columns[name][i] for name in feature_names]
            if drop_na and any(v is None or (isinstance(v, float) and math.isnan(v)) for v in row):
                continue
            rows.append(row)
            if labels_out is not None and labels is not None:
                labels_out.append(labels[i])

        return FeatureSet(
            feature_names=feature_names,
            data=rows,
            n_features=len(feature_names),
            n_observations=len(rows),
            labels=labels_out,
        )
