"""Causal ATR triple-barrier labels for OHLC research; never executes orders."""

from __future__ import annotations
import math
from typing import Sequence

LABELS = ("UP_FIRST", "DOWN_FIRST", "TIMEOUT", "AMBIGUOUS", "UNAVAILABLE")


def triple_barrier_label(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    atr: Sequence[float | None],
    start_index: int,
    *,
    upper_atr: float = 1.0,
    lower_atr: float = 1.0,
    vertical_barrier: int = 10,
) -> dict[str, int | float | str | None]:
    """Classify the first barrier touched using ATR fixed at signal close.

    A same-bar double touch is AMBIGUOUS. An incomplete vertical window is
    UNAVAILABLE, never mislabeled as TIMEOUT. OHLC validation is bounded to the
    event's own label window, keeping per-event work O(vertical_barrier).
    """
    n = len(closes)
    if not (len(opens) == len(highs) == len(lows) == len(atr) == n):
        raise ValueError("OHLC and ATR arrays must have equal lengths")
    if (
        isinstance(start_index, bool)
        or not isinstance(start_index, int)
        or not 0 <= start_index < n
    ):
        raise ValueError("start_index must be a valid row index")
    if (
        isinstance(vertical_barrier, bool)
        or not isinstance(vertical_barrier, int)
        or vertical_barrier < 1
    ):
        raise ValueError("vertical_barrier must be an integer >= 1")
    if not all(math.isfinite(x) and x > 0 for x in (upper_atr, lower_atr)):
        raise ValueError("ATR multipliers must be finite and positive")
    scale = atr[start_index]
    if scale is None or not math.isfinite(float(scale)) or float(scale) <= 0:
        return {
            "label": "UNAVAILABLE",
            "end_index": None,
            "upper_barrier": None,
            "lower_barrier": None,
        }
    upper = float(closes[start_index]) + upper_atr * float(scale)
    lower = float(closes[start_index]) - lower_atr * float(scale)
    stop = start_index + vertical_barrier
    for i in range(start_index, min(n, stop + 1)):
        o, h, lo, c = opens[i], highs[i], lows[i], closes[i]
        if not all(math.isfinite(float(x)) and float(x) > 0 for x in (o, h, lo, c)):
            raise ValueError(f"invalid OHLC at index {i}")
        if h < max(o, c, lo) or lo > min(o, c, h):
            raise ValueError(f"invalid OHLC geometry at index {i}")
    if stop >= n:
        return {
            "label": "UNAVAILABLE",
            "end_index": None,
            "upper_barrier": upper,
            "lower_barrier": lower,
        }
    for j in range(start_index + 1, stop + 1):
        if opens[j] >= upper:
            return {
                "label": "UP_FIRST",
                "end_index": j,
                "upper_barrier": upper,
                "lower_barrier": lower,
            }
        if opens[j] <= lower:
            return {
                "label": "DOWN_FIRST",
                "end_index": j,
                "upper_barrier": upper,
                "lower_barrier": lower,
            }
        hit_up, hit_down = highs[j] >= upper, lows[j] <= lower
        if hit_up and hit_down:
            return {
                "label": "AMBIGUOUS",
                "end_index": j,
                "upper_barrier": upper,
                "lower_barrier": lower,
            }
        if hit_up:
            return {
                "label": "UP_FIRST",
                "end_index": j,
                "upper_barrier": upper,
                "lower_barrier": lower,
            }
        if hit_down:
            return {
                "label": "DOWN_FIRST",
                "end_index": j,
                "upper_barrier": upper,
                "lower_barrier": lower,
            }
    return {"label": "TIMEOUT", "end_index": stop, "upper_barrier": upper, "lower_barrier": lower}


__all__ = ["LABELS", "triple_barrier_label"]
