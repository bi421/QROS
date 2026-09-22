"""Execution adapter for context-aware Phase 5.2 rebuild datasets."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from researchos.experiments.phase52.execution import _run_prepared
from researchos.experiments.phase52.experiment import Phase52Config
from researchos.experiments.phase52.macro_features import MacroFeatureBuilder
from researchos.experiments.phase52.prepared import Phase52PreparedData

from .context_pipeline import ContextAwareFeatureBuild
from .feature_contract import FEATURE_SET_NAMES, Phase52FeatureContract

_EXECUTION_FEATURE_SET_NAMES = {
    "PRICE_ONLY": "PRICE_ONLY",
    "PRICE_DXY": "PRICE + DXY",
    "PRICE_US10Y": "PRICE + US10Y",
    "PRICE_VIX": "PRICE + VIX",
    "PRICE_ALL": "PRICE + ALL",
}


@dataclass(frozen=True)
class _DatasetView:
    """Minimal execution view over the rebuild FeatureDataset contract."""

    feature_names: tuple[str, ...]
    features: tuple[tuple[float, ...], ...]
    labels: tuple[int, ...]
    metadata: dict[str, object]

    @property
    def sample_count(self) -> int:
        return len(self.features)


@dataclass(frozen=True)
class _PreparedView:
    """Phase 5.2 execution view backed exclusively by research observations."""

    close: tuple[float, ...]
    high: tuple[float, ...]
    low: tuple[float, ...]
    volume: tuple[float, ...]
    timestamps: tuple[str, ...]
    macro_timestamps: dict[str, tuple[str, ...]]
    macro_factor_series: dict[str, tuple[float | None, ...]]
    dataset: _DatasetView
    macro_diagnostics: Any
    input_provenance: dict[str, Any]

    @property
    def sample_count(self) -> int:
        return self.dataset.sample_count

    @property
    def source_indices(self) -> tuple[int, ...]:
        return tuple(self.dataset.metadata["source_indices"])  # type: ignore[arg-type]

    def validate(self, required_macro_symbols: tuple[str, ...]) -> None:
        if not (
            len(self.close)
            == len(self.high)
            == len(self.low)
            == len(self.volume)
            == len(self.timestamps)
        ):
            raise ValueError("Context execution price inputs must have equal length")
        for symbol in required_macro_symbols:
            if symbol not in self.macro_timestamps or symbol not in self.macro_factor_series:
                raise ValueError(f"Context execution missing macro symbol: {symbol}")
            if len(self.macro_timestamps[symbol]) != len(self.timestamps):
                raise ValueError(f"Context execution macro timestamps misaligned: {symbol}")
            if len(self.macro_factor_series[symbol]) != len(self.timestamps):
                raise ValueError(f"Context execution macro series misaligned: {symbol}")
        indices = self.source_indices
        if indices != tuple(range(self.sample_count)):
            raise ValueError("Context execution source indices must map 1:1 to research rows")

    def blocked_if_insufficient(self, train_size: int, validation_size: int):
        if self.sample_count < train_size + validation_size:
            from researchos.experiments.phase52.contracts import Phase52Result

            return Phase52Result.blocked(
                reason="REAL XAUUSD + MACRO DATA REQUIRED (insufficient aligned samples after merge)",
                macro_symbols_present=self.macro_diagnostics.symbols_present,
                macro_symbols_missing=self.macro_diagnostics.symbols_missing,
            )
        return None


def _prepared_view(
    build: ContextAwareFeatureBuild, feature_set: str, cfg: Phase52Config
) -> Phase52PreparedData:
    research = build.research_observations
    close = tuple(float(o.close) for o in research)
    high = tuple(float(o.high) for o in research)
    low = tuple(float(o.low) for o in research)
    volume = tuple(float(o.tick_volume) for o in research)
    timestamps = tuple(o.timestamp for o in research)
    macro: dict[str, tuple[float | None, ...]] = {
        "DXY": tuple(o.dxy for o in research),
        "US10Y": tuple(o.us10y for o in research),
        "VIX": tuple(o.vix for o in research),
    }
    macro_timestamps: dict[str, tuple[object, ...]] = {
        symbol: tuple(timestamps) for symbol in macro
    }
    return Phase52PreparedData.build(
        close,
        high,
        low,
        volume,
        timestamps,
        macro_timestamps,
        macro,
        horizon=cfg.horizon,
        threshold=cfg.threshold,
        required_macro_symbols=cfg.required_macro_symbols,
    )

def run_context_aware_phase52_comparison(
    build: ContextAwareFeatureBuild,
    config: Phase52Config | None = None,
) -> dict[str, Any]:
    """Execute every feature set using context-initialized research features."""
    cfg = config or Phase52Config()
    contract = Phase52FeatureContract(
        horizon=cfg.horizon,
        threshold=cfg.threshold,
        warmup=60,
        train_size=cfg.train_size,
        validation_size=cfg.validation_size,
    )
    build.validate(contract)

    results: dict[str, Any] = {}
    for feature_set in FEATURE_SET_NAMES:
        prepared = _prepared_view(build, feature_set, cfg)
        results[feature_set] = _run_prepared(
            prepared,
            replace(cfg, feature_set=_EXECUTION_FEATURE_SET_NAMES[feature_set]),
        )
    return results


__all__ = ["run_context_aware_phase52_comparison"]
