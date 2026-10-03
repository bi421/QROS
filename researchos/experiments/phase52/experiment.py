"""
Phase 5.2 — deterministic walk-forward macro-augmented predictive-value
experiment.

Reuses the frozen Phase 5.1 primitives unmodified. Feature-set comparisons
are explicit and use a deterministic multivariate estimator inside Phase 5.2.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from .contracts import Phase52Result
from .prepared import Phase52PreparedData


class _ProbabilityEstimator(Protocol):
    def predict_proba(self, feature_row: Sequence[float | None]) -> dict[int, float]: ...

FEATURE_SET_NAMES: tuple[str, ...] = (
    "PRICE_ONLY",
    "PRICE + DXY",
    "PRICE + US10Y",
    "PRICE + VIX",
    "PRICE + ALL",
)


@dataclass
class Phase52Config:
    symbol: str = "XAUUSD"
    timeframe: str = "1d"
    horizon: int = 5
    threshold: float = 0.0
    train_size: int = 1200
    validation_size: int = 200
    step_size: int = 200
    n_bins: int = 10
    min_sample_count: int = 100
    significance_level: float = 0.05
    spread_spec: str = "fixed:0.0"
    slippage_spec: str = "fixed:0.0"
    commission_spec: str = "fixed:0.0"
    cost_applied: bool = True
    estimator_feature: int | None = None
    feature_set: str = "PRICE + DXY"
    n_neighbors: int = 25
    holdout_size: int = 40
    required_macro_symbols: tuple[str, ...] = ("DXY", "US10Y", "VIX")


def _resolve_feature_indices(
    config: Phase52Config, names: Sequence[str], metadata: Mapping[str, object]
) -> tuple[int, ...]:
    if config.estimator_feature is not None:
        return (int(config.estimator_feature),)
    if config.feature_set not in FEATURE_SET_NAMES:
        raise ValueError(f"Unsupported Phase 5.2 feature set: {config.feature_set}")
    price_count_value = metadata.get("price_feature_count")
    if not isinstance(price_count_value, int):
        raise ValueError("Dataset metadata missing integer price_feature_count")
    price_count = price_count_value
    if config.feature_set == "PRICE_ONLY":
        return tuple(range(price_count))
    selected_symbols = {
        "PRICE + DXY": ("DXY",),
        "PRICE + US10Y": ("US10Y",),
        "PRICE + VIX": ("VIX",),
        "PRICE + ALL": ("DXY", "US10Y", "VIX"),
    }[config.feature_set]
    indices = list(range(price_count))
    for symbol in selected_symbols:
        indices.extend(i for i, name in enumerate(names) if name.startswith(f"macro_{symbol}_"))
    if len(indices) != price_count + 3 * len(selected_symbols):
        raise ValueError(f"Feature set {config.feature_set} is missing expected macro features")
    return tuple(indices)


def run_phase52(
    close: Sequence[float],
    high: Sequence[float],
    low: Sequence[float],
    volume: Sequence[float],
    macro_factor_series: dict[str, Sequence[float | None]],
    config: Phase52Config | None = None,
    *,
    timestamps: Sequence[object] | None = None,
    macro_timestamps: dict[str, Sequence[object]] | None = None,
) -> Phase52Result:
    """Run one Phase 5.2 feature-set experiment through the governed execution path."""
    cfg = config or Phase52Config()
    if timestamps is None or macro_timestamps is None:
        return Phase52Result.blocked(
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
            reason="EXPLICIT UTC TIMESTAMP ALIGNMENT REQUIRED FOR PHASE 5.2",
        )
    try:
        prepared = Phase52PreparedData.build(
            close,
            high,
            low,
            volume,
            timestamps,
            macro_timestamps,
            macro_factor_series,
            horizon=cfg.horizon,
            threshold=cfg.threshold,
            required_macro_symbols=cfg.required_macro_symbols,
        )
    except (TypeError, ValueError) as exc:
        message = str(exc)
        missing_symbols: tuple[str, ...] = ()

        macro_markers = (
            "Prepared inputs missing required macro symbol: ",
            "Prepared macro timestamps misaligned: ",
            "Prepared macro series misaligned: ",
        )

        for marker in macro_markers:
            if marker in message:
                symbol = message.split(marker, 1)[1].strip()
                if symbol:
                    missing_symbols = (symbol,)
                break

        return Phase52Result.blocked(
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
            reason=f"PHASE 5.2 INPUT CONTRACT FAILED: {message}",
            macro_symbols_missing=missing_symbols,
        )

    from .execution import _run_prepared

    return _run_prepared(prepared, cfg)


def run_phase52_comparison(
    close: Sequence[float],
    high: Sequence[float],
    low: Sequence[float],
    volume: Sequence[float],
    macro_factor_series: dict[str, Sequence[float | None]],
    config: Phase52Config | None = None,
    *,
    timestamps: Sequence[object] | None = None,
    macro_timestamps: dict[str, Sequence[object]] | None = None,
) -> dict[str, Phase52Result]:
    """Run all five feature sets with the governed final-holdout contract."""
    base = config or Phase52Config()
    kwargs_without_config = dict(kwargs)
    kwargs_without_config.pop("config", None)
    return {
        feature_set: run_phase52(
            close,
            high,
            low,
            volume,
            macro_factor_series,
            config=replace(base, feature_set=feature_set),
            timestamps=timestamps,
            macro_timestamps=macro_timestamps,
        )
        for feature_set in FEATURE_SET_NAMES
    }


__all__ = ["FEATURE_SET_NAMES", "Phase52Config", "run_phase52", "run_phase52_comparison"]
