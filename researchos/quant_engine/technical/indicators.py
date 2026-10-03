"""
Technical Analysis Engine — vectorized indicator implementations.

Every indicator is a pure function of the input series (and parameters).
All functions are deterministic: same inputs → same outputs. Series are
returned aligned to the input length with ``None`` warm-up padding so that
downstream batch computations are trivially index-aligned.

This module contains NO trading logic, NO signals, NO execution.
Research-only numerical computation.
"""

from __future__ import annotations

import math

from researchos.quant_engine.technical.contracts import Bars

# ──────────────────────────────────────────────
# Internal helpers (vectorized-style, pure)
# ──────────────────────────────────────────────


def _sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def _ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) == 0:
        return out
    alpha = 2.0 / (period + 1.0)
    prev: float | None = None
    for i, v in enumerate(values):
        if prev is None:
            prev = v
        else:
            prev = alpha * v + (1.0 - alpha) * prev
        out[i] = prev
    return out


def _wma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    weight_sum = period * (period + 1) / 2.0
    for i in range(period - 1, len(values)):
        total = 0.0
        for j in range(period):
            total += values[i - j] * (period - j)
        out[i] = total / weight_sum
    return out


def _wilder_rma(values: list[float], period: int) -> list[float | None]:
    """Wilder's smoothing (RMA) used by RSI / ATR / ADX."""
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    alpha = 1.0 / period
    prev: float | None = None
    for i, v in enumerate(values):
        if i == period - 1:
            # First RMA = simple mean of first `period` values.
            prev = sum(values[:period]) / period
        elif i >= period:
            if prev is None:
                raise RuntimeError("Wilder RMA state missing after warm-up")
            prev = alpha * v + (1.0 - alpha) * prev
        if i >= period - 1:
            out[i] = prev
    return out


def _true_range(bars: Bars) -> list[float]:
    tr: list[float] = []
    for i in range(bars.length):
        if i == 0:
            tr.append(bars.high[0] - bars.low[0])
        else:
            prev_close = bars.close[i - 1]
            tr.append(
                max(
                    bars.high[i] - bars.low[i],
                    abs(bars.high[i] - prev_close),
                    abs(bars.low[i] - prev_close),
                )
            )
    return tr


def _pad(values: list[float], warmup: int) -> list[float | None]:
    """Pad the front of a series with None so it aligns to input length."""
    return [None] * warmup + list(values)


# ──────────────────────────────────────────────
# Trend indicators
# ──────────────────────────────────────────────


def sma(bars: Bars, period: int = 20) -> list[float | None]:
    return _sma(bars.close, period)


def ema(bars: Bars, period: int = 20) -> list[float | None]:
    return _ema(bars.close, period)


def wma(bars: Bars, period: int = 20) -> list[float | None]:
    return _wma(bars.close, period)


def hma(bars: Bars, period: int = 20) -> list[float | None]:
    """
    Hull Moving Average.

    HMA = WMA(2*WMA(n/2) - WMA(n), sqrt(n))
    """
    n = period
    half = max(1, int(n / 2))
    wma_half = _wma(bars.close, half)
    wma_full = _wma(bars.close, n)

    length = len(bars.close)
    raw: list[float | None] = [None] * length
    for i in range(length):
        if wma_half[i] is not None and wma_full[i] is not None:
            raw[i] = 2.0 * wma_half[i] - wma_full[i]  # type: ignore[operator]

    # WMA over the raw series, skipping None warm-up.
    sqrt_n = max(1, int(math.sqrt(n)))
    out: list[float | None] = [None] * length
    weight_sum = sqrt_n * (sqrt_n + 1) / 2.0
    for i in range(length):
        if raw[i] is None:
            continue
        if i - sqrt_n + 1 < 0:
            continue
        total = 0.0
        ok = True
        for j in range(sqrt_n):
            if raw[i - j] is None:
                ok = False
                break
            total += raw[i - j] * (sqrt_n - j)  # type: ignore[operator]
        if ok:
            out[i] = total / weight_sum
    return out


def vwma(bars: Bars, period: int = 20) -> list[float | None]:
    """Volume-Weighted Moving Average."""
    length = bars.length
    out: list[float | None] = [None] * length
    if length < period or period <= 0:
        return out
    pv = 0.0
    vol = 0.0
    for i in range(length):
        pv += bars.close[i] * bars.volume[i]
        vol += bars.volume[i]
        if i >= period:
            pv -= bars.close[i - period] * bars.volume[i - period]
            vol -= bars.volume[i - period]
        if i >= period - 1:
            out[i] = pv / vol if vol != 0 else 0.0
    return out


# ──────────────────────────────────────────────
# Momentum indicators
# ──────────────────────────────────────────────


def rsi(bars: Bars, period: int = 14) -> list[float | None]:
    """Relative Strength Index (Wilder's smoothing)."""
    length = bars.length
    out: list[float | None] = [None] * length
    if length < period + 1:
        return out

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, length):
        delta = bars.close[i] - bars.close[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = _wilder_rma(gains, period)
    avg_loss = _wilder_rma(losses, period)

    for i in range(period - 1, len(gains)):
        g = avg_gain[i]
        avg_loss_val = avg_loss[i]
        if g is None or avg_loss_val is None:
            continue
        if avg_loss_val == 0:
            out[i + 1] = 100.0
        else:
            rs = g / avg_loss_val
            out[i + 1] = 100.0 - (100.0 / (1.0 + rs))
    return out


def stochastic(
    bars: Bars,
    period: int = 14,
    smooth_k: int = 3,
    smooth_d: int = 3,
) -> dict[str, list[float | None]]:
    """Stochastic Oscillator (%K and %D)."""
    length = bars.length
    raw_k: list[float | None] = [None] * length
    if length < period:
        return {"k": raw_k, "d": [None] * length}

    for i in range(period - 1, length):
        highest = max(bars.high[i - period + 1 : i + 1])
        lowest = min(bars.low[i - period + 1 : i + 1])
        if highest == lowest:
            raw_k[i] = 50.0
        else:
            raw_k[i] = (bars.close[i] - lowest) / (highest - lowest) * 100.0

    k = _sma([v for v in raw_k if v is not None], smooth_k) if smooth_k > 0 else raw_k
    # Re-align smoothed K.
    k_aligned: list[float | None] = [None] * length
    idx = 0
    for i in range(length):
        if raw_k[i] is not None:
            if idx < len(k) and k[idx] is not None:
                k_aligned[i] = k[idx]
            idx += 1

    k_vals = [v for v in k_aligned if v is not None]
    d = _sma(k_vals, smooth_d) if smooth_d > 0 else k_vals
    d_aligned: list[float | None] = [None] * length
    di = 0
    for i in range(length):
        if k_aligned[i] is not None:
            if di < len(d) and d[di] is not None:
                d_aligned[i] = d[di]
            di += 1

    return {"k": k_aligned, "d": d_aligned}


def cci(bars: Bars, period: int = 20) -> list[float | None]:
    """Commodity Channel Index."""
    length = bars.length
    out: list[float | None] = [None] * length
    if length < period:
        return out
    tp = [(h + low + c) / 3.0 for h, low, c in zip(bars.high, bars.low, bars.close)]
    tp_sma = _sma(tp, period)
    for i in range(period - 1, length):
        mean = tp_sma[i]
        if mean is None:
            continue
        deviation = sum(abs(tp[j] - mean) for j in range(i - period + 1, i + 1)) / period
        if deviation == 0:
            out[i] = 0.0
        else:
            out[i] = (tp[i] - mean) / (0.015 * deviation)
    return out


def roc(bars: Bars, period: int = 12) -> list[float | None]:
    """Rate of Change (percent)."""
    length = bars.length
    out: list[float | None] = [None] * length
    for i in range(period, length):
        prev = bars.close[i - period]
        if prev == 0:
            out[i] = 0.0
        else:
            out[i] = (bars.close[i] - prev) / prev * 100.0
    return out


def momentum(bars: Bars, period: int = 12) -> list[float | None]:
    """Momentum (absolute change)."""
    length = bars.length
    out: list[float | None] = [None] * length
    for i in range(period, length):
        out[i] = bars.close[i] - bars.close[i - period]
    return out


# ──────────────────────────────────────────────
# Volatility indicators
# ──────────────────────────────────────────────


def atr(bars: Bars, period: int = 14) -> list[float | None]:
    """Average True Range (Wilder's)."""
    tr = _true_range(bars)
    return _wilder_rma(tr, period)


def bollinger_bands(
    bars: Bars,
    period: int = 20,
    std_dev: float = 2.0,
) -> dict[str, list[float | None]]:
    """Bollinger Bands (upper, middle, lower)."""
    length = bars.length
    middle = _sma(bars.close, period)
    upper: list[float | None] = [None] * length
    lower: list[float | None] = [None] * length
    for i in range(period - 1, length):
        m = middle[i]
        if m is None:
            continue
        window = bars.close[i - period + 1 : i + 1]
        mean = sum(window) / period
        var = sum((x - mean) ** 2 for x in window) / period
        sd = math.sqrt(var)
        upper[i] = m + std_dev * sd
        lower[i] = m - std_dev * sd
    return {"upper": upper, "middle": middle, "lower": lower}


def keltner_channel(
    bars: Bars,
    period: int = 20,
    atr_period: int = 10,
    multiplier: float = 2.0,
) -> dict[str, list[float | None]]:
    """Keltner Channel (upper, middle, lower) using EMA + ATR."""
    middle = _ema(bars.close, period)
    atr_vals = atr(bars, atr_period)
    length = bars.length
    upper: list[float | None] = [None] * length
    lower: list[float | None] = [None] * length
    for i in range(length):
        middle_value = middle[i]
        atr_value = atr_vals[i]
        if middle_value is not None and atr_value is not None:
            upper[i] = middle_value + multiplier * atr_value
            lower[i] = middle_value - multiplier * atr_value
    return {"upper": upper, "middle": middle, "lower": lower}


def donchian_channel(
    bars: Bars,
    period: int = 20,
) -> dict[str, list[float | None]]:
    """Donchian Channel (upper, middle, lower)."""
    length = bars.length
    upper: list[float | None] = [None] * length
    lower: list[float | None] = [None] * length
    middle: list[float | None] = [None] * length
    for i in range(period - 1, length):
        window_high = bars.high[i - period + 1 : i + 1]
        window_low = bars.low[i - period + 1 : i + 1]
        u = max(window_high)
        lower_val = min(window_low)
        upper[i] = u
        lower[i] = lower_val
        middle[i] = (u + lower_val) / 2.0
    return {"upper": upper, "middle": middle, "lower": lower}


# ──────────────────────────────────────────────
# Volume indicators
# ──────────────────────────────────────────────


def obv(bars: Bars) -> list[float | None]:
    """On-Balance Volume."""
    length = bars.length
    out: list[float | None] = [None] * length
    if length == 0:
        return out
    out[0] = bars.volume[0]
    for i in range(1, length):
        previous = out[i - 1]
        if previous is None:
            raise RuntimeError("OBV state missing after initialization")
        if bars.close[i] > bars.close[i - 1]:
            out[i] = previous + bars.volume[i]
        elif bars.close[i] < bars.close[i - 1]:
            out[i] = previous - bars.volume[i]
        else:
            out[i] = previous
    return out


def vwap(bars: Bars) -> list[float | None]:
    """Session VWAP over the provided bar series (cumulative)."""
    length = bars.length
    out: list[float | None] = [None] * length
    pv = 0.0
    vol = 0.0
    for i in range(length):
        typical = (bars.high[i] + bars.low[i] + bars.close[i]) / 3.0
        pv += typical * bars.volume[i]
        vol += bars.volume[i]
        if vol != 0:
            out[i] = pv / vol
        else:
            out[i] = bars.close[i]
    return out


def mfi(bars: Bars, period: int = 14) -> list[float | None]:
    """Money Flow Index."""
    length = bars.length
    out: list[float | None] = [None] * length
    if length < period + 1:
        return out
    typical = [(h + low + c) / 3.0 for h, low, c in zip(bars.high, bars.low, bars.close)]
    raw_money = [t * v for t, v in zip(typical, bars.volume)]

    pos: list[float] = []
    neg: list[float] = []
    for i in range(1, length):
        if typical[i] > typical[i - 1]:
            pos.append(raw_money[i])
            neg.append(0.0)
        elif typical[i] < typical[i - 1]:
            pos.append(0.0)
            neg.append(raw_money[i])
        else:
            pos.append(0.0)
            neg.append(0.0)

    pos_sum = _wilder_rma(pos, period)
    neg_sum = _wilder_rma(neg, period)
    for i in range(period - 1, len(pos)):
        p = pos_sum[i]
        n = neg_sum[i]
        if p is None or n is None:
            continue
        if n == 0:
            out[i + 1] = 100.0
        else:
            ratio = p / n
            out[i + 1] = 100.0 - (100.0 / (1.0 + ratio))
    return out


def cmf(bars: Bars, period: int = 20) -> list[float | None]:
    """Chaikin Money Flow."""
    length = bars.length
    out: list[float | None] = [None] * length
    if length < period:
        return out
    for i in range(period - 1, length):
        mfm_sum = 0.0
        vol_sum = 0.0
        for j in range(i - period + 1, i + 1):
            high = bars.high[j]
            low = bars.low[j]
            close = bars.close[j]
            if high != low:
                mfm = ((close - low) - (high - close)) / (high - low)
            else:
                mfm = 0.0
            mfm_sum += mfm * bars.volume[j]
            vol_sum += bars.volume[j]
        out[i] = mfm_sum / vol_sum if vol_sum != 0 else 0.0
    return out


def accumulation_distribution(bars: Bars) -> list[float | None]:
    """Accumulation / Distribution Line."""
    length = bars.length
    out: list[float | None] = [None] * length
    ad = 0.0
    for i in range(length):
        high = bars.high[i]
        low = bars.low[i]
        close = bars.close[i]
        if high != low:
            clv = ((close - low) - (high - close)) / (high - low)
        else:
            clv = 0.0
        ad += clv * bars.volume[i]
        out[i] = ad
    return out


# ──────────────────────────────────────────────
# Trend strength indicators
# ──────────────────────────────────────────────


def dmi(bars: Bars, period: int = 14) -> dict[str, list[float | None]]:
    """
    Directional Movement Indicators: +DI, -DI, ADX, ADXR.

    Returns dict with keys "+di", "-di", "adx", "adxr".
    """
    length = bars.length
    plus_dm: list[float] = [0.0] * length
    minus_dm: list[float] = [0.0] * length
    tr = _true_range(bars)

    for i in range(1, length):
        up_move = bars.high[i] - bars.high[i - 1]
        down_move = bars.low[i - 1] - bars.low[i]
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0

    tr_rma = _wilder_rma(tr, period)
    plus_rma = _wilder_rma(plus_dm, period)
    minus_rma = _wilder_rma(minus_dm, period)

    plus_di: list[float | None] = [None] * length
    minus_di: list[float | None] = [None] * length
    dx: list[float | None] = [None] * length

    for i in range(length):
        t = tr_rma[i]
        p = plus_rma[i]
        m = minus_rma[i]
        if t is None or p is None or m is None:
            continue
        if t == 0:
            plus_di[i] = 0.0
            minus_di[i] = 0.0
            continue
        plus_value = 100.0 * p / t
        minus_value = 100.0 * m / t
        plus_di[i] = plus_value
        minus_di[i] = minus_value
        s = plus_value + minus_value
        if s == 0:
            dx[i] = 0.0
        else:
            dx[i] = 100.0 * abs(plus_value - minus_value) / s

    dx_vals = [v for v in dx if v is not None]
    adx_raw = _wilder_rma(dx_vals, period)
    adx: list[float | None] = [None] * length
    idx = 0
    for i in range(length):
        if dx[i] is not None:
            if idx < len(adx_raw) and adx_raw[idx] is not None:
                adx[i] = adx_raw[idx]
            idx += 1

    adxr: list[float | None] = [None] * length
    for i in range(length):
        if adx[i] is not None:
            prev = adx[i - period] if i - period >= 0 else None
            adx_value = adx[i]
            if prev is not None and adx_value is not None:
                adxr[i] = (adx_value + prev) / 2.0

    return {"+di": plus_di, "-di": minus_di, "adx": adx, "adxr": adxr}


def adx(bars: Bars, period: int = 14) -> list[float | None]:
    return dmi(bars, period)["adx"]


# ──────────────────────────────────────────────
# MACD family
# ──────────────────────────────────────────────


def macd(
    bars: Bars,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, list[float | None]]:
    """MACD line, signal line, and histogram."""
    ema_fast = _ema(bars.close, fast)
    ema_slow = _ema(bars.close, slow)
    length = bars.length

    macd_line: list[float | None] = [None] * length
    for i in range(length):
        fast_value = ema_fast[i]
        slow_value = ema_slow[i]
        if fast_value is not None and slow_value is not None:
            macd_line[i] = fast_value - slow_value

    macd_vals = [v for v in macd_line if v is not None]
    signal_raw = _ema(macd_vals, signal)
    signal_line: list[float | None] = [None] * length
    idx = 0
    for i in range(length):
        if macd_line[i] is not None:
            if idx < len(signal_raw) and signal_raw[idx] is not None:
                signal_line[i] = signal_raw[idx]
            idx += 1

    histogram: list[float | None] = [None] * length
    for i in range(length):
        macd_value = macd_line[i]
        signal_value = signal_line[i]
        if macd_value is not None and signal_value is not None:
            histogram[i] = macd_value - signal_value

    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram,
    }


# ──────────────────────────────────────────────
# SuperTrend, Ichimoku Cloud, Parabolic SAR
# ──────────────────────────────────────────────


def supertrend(
    bars: Bars,
    period: int = 10,
    multiplier: float = 3.0,
) -> dict[str, list[float | None]]:
    """
    SuperTrend indicator.

    Returns dict containing:
        - supertrend: SuperTrend series
        - upper_band: Final upper band series
        - lower_band: Final lower band series
        - trend: Trend direction (+1.0 for bullish, -1.0 for bearish)
    """
    length = bars.length
    atr_series = atr(bars, period)
    supertrend_out: list[float | None] = [None] * length
    upper_band_out: list[float | None] = [None] * length
    lower_band_out: list[float | None] = [None] * length
    trend_out: list[float | None] = [None] * length

    if length == 0 or period <= 0:
        return {
            "supertrend": supertrend_out,
            "upper_band": upper_band_out,
            "lower_band": lower_band_out,
            "trend": trend_out,
        }

    prev_upper: float | None = None
    prev_lower: float | None = None
    prev_trend: float = 1.0

    for i in range(length):
        atr_val = atr_series[i]
        if atr_val is None:
            continue

        hl2 = (bars.high[i] + bars.low[i]) / 2.0
        basic_upper = hl2 + multiplier * atr_val
        basic_lower = hl2 - multiplier * atr_val

        if prev_upper is None or prev_lower is None:
            final_upper = basic_upper
            final_lower = basic_lower
            curr_trend = 1.0
        else:
            if basic_upper < prev_upper or bars.close[i - 1] > prev_upper:
                final_upper = basic_upper
            else:
                final_upper = prev_upper

            if basic_lower > prev_lower or bars.close[i - 1] < prev_lower:
                final_lower = basic_lower
            else:
                final_lower = prev_lower

            if prev_trend == 1.0:
                if bars.close[i] < final_lower:
                    curr_trend = -1.0
                else:
                    curr_trend = 1.0
            else:
                if bars.close[i] > final_upper:
                    curr_trend = 1.0
                else:
                    curr_trend = -1.0

        st_val = final_lower if curr_trend == 1.0 else final_upper

        upper_band_out[i] = final_upper
        lower_band_out[i] = final_lower
        trend_out[i] = curr_trend
        supertrend_out[i] = st_val

        prev_upper = final_upper
        prev_lower = final_lower
        prev_trend = curr_trend

    return {
        "supertrend": supertrend_out,
        "upper_band": upper_band_out,
        "lower_band": lower_band_out,
        "trend": trend_out,
    }


def ichimoku_cloud(
    bars: Bars,
    tenkan_period: int = 9,
    kijun_period: int = 26,
    senkou_b_period: int = 52,
    displacement: int = 26,
) -> dict[str, list[float | None]]:
    """
    Ichimoku Kinko Hyo (Cloud) indicator.

    Returns dict containing:
        - tenkan_sen: Conversion Line
        - kijun_sen: Base Line
        - senkou_span_a: Leading Span A
        - senkou_span_b: Leading Span B
        - chikou_span: Lagging Span
    """
    length = bars.length
    tenkan: list[float | None] = [None] * length
    kijun: list[float | None] = [None] * length
    senkou_a: list[float | None] = [None] * length
    senkou_b: list[float | None] = [None] * length
    chikou: list[float | None] = [None] * length

    def _hl_mid(start_idx: int, end_idx: int) -> float:
        h = max(bars.high[start_idx : end_idx + 1])
        low_val = min(bars.low[start_idx : end_idx + 1])
        return (h + low_val) / 2.0

    for i in range(length):
        if i >= tenkan_period - 1:
            tenkan[i] = _hl_mid(i - tenkan_period + 1, i)
        if i >= kijun_period - 1:
            kijun[i] = _hl_mid(i - kijun_period + 1, i)

        if i >= displacement:
            src_idx = i - displacement
            t_val = tenkan[src_idx]
            k_val = kijun[src_idx]
            if t_val is not None and k_val is not None:
                senkou_a[i] = (t_val + k_val) / 2.0

            if src_idx >= senkou_b_period - 1:
                senkou_b[i] = _hl_mid(src_idx - senkou_b_period + 1, src_idx)

        if i + displacement < length:
            chikou[i] = bars.close[i + displacement]

    return {
        "tenkan_sen": tenkan,
        "kijun_sen": kijun,
        "senkou_span_a": senkou_a,
        "senkou_span_b": senkou_b,
        "chikou_span": chikou,
    }


def parabolic_sar(
    bars: Bars,
    af_step: float = 0.02,
    af_max: float = 0.2,
) -> dict[str, list[float | None]]:
    """
    Parabolic Stop and Reverse (PSAR) indicator.

    Returns dict containing:
        - psar: Parabolic SAR values
        - trend: Trend direction (+1.0 for uptrend, -1.0 for downtrend)
    """
    length = bars.length
    psar_out: list[float | None] = [None] * length
    trend_out: list[float | None] = [None] * length

    if length < 2:
        return {"psar": psar_out, "trend": trend_out}

    # Initial direction based on bar 1 vs bar 0 close
    is_uptrend = bars.close[1] >= bars.close[0]
    trend = 1.0 if is_uptrend else -1.0
    af = af_step
    ep = bars.high[1] if is_uptrend else bars.low[1]
    sar = bars.low[0] if is_uptrend else bars.high[0]

    psar_out[1] = sar
    trend_out[1] = trend

    for i in range(2, length):
        next_sar = sar + af * (ep - sar)

        if is_uptrend:
            next_sar = min(next_sar, bars.low[i - 1], bars.low[i - 2])
            if bars.low[i] < next_sar:
                is_uptrend = False
                trend = -1.0
                sar = ep
                ep = bars.low[i]
                af = af_step
            else:
                trend = 1.0
                sar = next_sar
                if bars.high[i] > ep:
                    ep = bars.high[i]
                    af = min(af + af_step, af_max)
        else:
            next_sar = max(next_sar, bars.high[i - 1], bars.high[i - 2])
            if bars.high[i] > next_sar:
                is_uptrend = True
                trend = 1.0
                sar = ep
                ep = bars.high[i]
                af = af_step
            else:
                trend = -1.0
                sar = next_sar
                if bars.low[i] < ep:
                    ep = bars.low[i]
                    af = min(af + af_step, af_max)

        psar_out[i] = sar
        trend_out[i] = trend

    return {
        "psar": psar_out,
        "trend": trend_out,
    }
