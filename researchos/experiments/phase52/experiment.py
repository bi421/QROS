"""
Phase 5.2 — deterministic walk-forward macro-augmented predictive-value
experiment.

Reuses the frozen Phase 5.1 primitives unmodified. Feature-set comparisons
are explicit and use a deterministic multivariate estimator inside Phase 5.2.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from researchos.experiments.phase51.baseline import baseline_always_predict
from researchos.experiments.phase51.calibration import _brier_from_proba, evaluate_calibration
from researchos.experiments.phase51.cost import apply_costs
from researchos.experiments.phase51.probability import EmpiricalProbabilityEstimator
from researchos.experiments.phase51.self_validation import aggregate_outcome
from researchos.experiments.phase51.statistics import evaluate_significance

from .alignment import validate_exact_timestamp_alignment
from .contracts import BaselineResult, ModelResult, Phase52Result
from .dataset import build_macro_augmented_dataset
from .multivariate import MultivariateEmpiricalProbabilityEstimator
from .provenance import build_input_provenance

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
    required_macro_symbols: tuple[str, ...] = ("DXY", "US10Y", "VIX")


def _resolve_feature_indices(
    config: Phase52Config, names: Sequence[str], metadata: dict
) -> tuple[int, ...]:
    if config.estimator_feature is not None:
        return (int(config.estimator_feature),)
    if config.feature_set not in FEATURE_SET_NAMES:
        raise ValueError(f"Unsupported Phase 5.2 feature set: {config.feature_set}")
    price_count = int(metadata["price_feature_count"])
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


def _evaluate_model(
    est: EmpiricalProbabilityEstimator | MultivariateEmpiricalProbabilityEstimator,
    val_features: Sequence[Sequence[float]],
    val_labels: Sequence[float],
) -> tuple[ModelResult, list[int], list[dict[int, float]]]:
    preds: list[int] = []
    probs: list[dict[int, float]] = []
    for row in val_features:
        row_probs = est.predict_proba(row)
        probs.append(row_probs)
        best = 1
        best_prob = -1.0
        for cls in (1, 0, -1):
            if row_probs[cls] > best_prob:
                best_prob = row_probs[cls]
                best = cls
        preds.append(best)
    acc = (
        sum(1 for p, a in zip(preds, val_labels) if int(p) == int(a)) / len(val_labels)
        if val_labels
        else 0.0
    )
    brier = _brier_from_proba(probs, val_labels)

    def _prec(pp: int) -> float:
        tp = sum(1 for p, a in zip(preds, val_labels) if int(p) == pp and int(a) == pp)
        fp = sum(1 for p, a in zip(preds, val_labels) if int(p) == pp and int(a) != pp)
        return tp / (tp + fp) if (tp + fp) else 0.0

    def _rec(pp: int) -> float:
        tp = sum(1 for p, a in zip(preds, val_labels) if int(p) == pp and int(a) == pp)
        fn = sum(1 for p, a in zip(preds, val_labels) if int(p) != pp and int(a) == pp)
        return tp / (tp + fn) if (tp + fn) else 0.0

    return (
        ModelResult(
            accuracy=acc,
            precision_up=_prec(1),
            precision_down=_prec(-1),
            recall_up=_rec(1),
            recall_down=_rec(-1),
            brier_score=brier,
            sample_count=len(val_labels),
        ),
        preds,
        probs,
    )


def _baseline_like(predictions: Sequence[int], actuals: Sequence[float]) -> BaselineResult:
    acc = (
        sum(1 for p, a in zip(predictions, actuals) if int(p) == int(a)) / len(actuals)
        if actuals
        else 0.0
    )
    n = len(actuals)
    brier = 0.0
    for p, a in zip(predictions, actuals):
        prob = [0.0, 0.0, 0.0]
        prob[int(p) + 1] = 1.0
        target = [0.0, 0.0, 0.0]
        target[int(a) + 1] = 1.0
        brier += sum((pi - ti) ** 2 for pi, ti in zip(prob, target))
    brier = brier / n / 3.0 if n else 0.0

    def _prec(pp: int) -> float:
        tp = sum(1 for p, a in zip(predictions, actuals) if int(p) == pp and int(a) == pp)
        fp = sum(1 for p, a in zip(predictions, actuals) if int(p) == pp and int(a) != pp)
        return tp / (tp + fp) if (tp + fp) else 0.0

    def _rec(pp: int) -> float:
        tp = sum(1 for p, a in zip(predictions, actuals) if int(p) == pp and int(a) == pp)
        fn = sum(1 for p, a in zip(predictions, actuals) if int(p) != pp and int(a) == pp)
        return tp / (tp + fn) if (tp + fn) else 0.0

    freqs = {"-1": 0.0, "0": 0.0, "1": 0.0}
    for a in actuals:
        freqs[str(int(a))] = freqs.get(str(int(a)), 0.0) + 1.0
    total = sum(freqs.values()) or 1.0
    freqs = {k: v / total for k, v in freqs.items()}
    return BaselineResult(
        accuracy=acc,
        precision_up=_prec(1),
        precision_down=_prec(-1),
        recall_up=_rec(1),
        recall_down=_rec(-1),
        brier_score=brier,
        class_frequencies=freqs,
        sample_count=len(actuals),
    )


def _model_like(
    predictions: Sequence[int], actuals: Sequence[float], probs: Sequence[dict[int, float]]
) -> ModelResult:
    acc = (
        sum(1 for p, a in zip(predictions, actuals) if int(p) == int(a)) / len(actuals)
        if actuals
        else 0.0
    )
    brier = _brier_from_proba(probs, actuals)

    def _prec(pp: int) -> float:
        tp = sum(1 for p, a in zip(predictions, actuals) if int(p) == pp and int(a) == pp)
        fp = sum(1 for p, a in zip(predictions, actuals) if int(p) == pp and int(a) != pp)
        return tp / (tp + fp) if (tp + fp) else 0.0

    def _rec(pp: int) -> float:
        tp = sum(1 for p, a in zip(predictions, actuals) if int(p) == pp and int(a) == pp)
        fn = sum(1 for p, a in zip(predictions, actuals) if int(p) != pp and int(a) == pp)
        return tp / (tp + fn) if (tp + fn) else 0.0

    return ModelResult(
        accuracy=acc,
        precision_up=_prec(1),
        precision_down=_prec(-1),
        recall_up=_rec(1),
        recall_down=_rec(-1),
        brier_score=brier,
        sample_count=len(actuals),
    )


def run_phase52(
    close,
    high,
    low,
    volume,
    macro_factor_series: dict[str, Sequence[float | None]],
    config: Phase52Config | None = None,
    *,
    timestamps: Sequence[object] | None = None,
    macro_timestamps: dict[str, Sequence[object]] | None = None,
) -> Phase52Result:
    """Run one explicit Phase 5.2 feature-set experiment."""
    cfg = config or Phase52Config()
    if timestamps is None or macro_timestamps is None:
        return Phase52Result.blocked(
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
            reason="EXPLICIT UTC TIMESTAMP ALIGNMENT REQUIRED FOR PHASE 5.2",
        )
    target_timestamps = list(timestamps)
    if len(target_timestamps) != len(close):
        return Phase52Result.blocked(
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
            reason="XAUUSD TIMESTAMP LENGTH DOES NOT MATCH PRICE DATA",
        )
    missing_timestamps = [s for s in cfg.required_macro_symbols if s not in macro_timestamps]
    if missing_timestamps:
        return Phase52Result.blocked(
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
            reason=f"REQUIRED MACRO TIMESTAMPS MISSING: {', '.join(missing_timestamps)}",
            macro_symbols_missing=tuple(missing_timestamps),
        )
    try:
        for symbol in cfg.required_macro_symbols:
            validate_exact_timestamp_alignment(target_timestamps, macro_timestamps[symbol], symbol)
    except ValueError as exc:
        return Phase52Result.blocked(
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
            reason=f"EXACT TIMESTAMP ALIGNMENT FAILED: {exc}",
        )
    if len(close) < cfg.train_size + cfg.validation_size:
        return Phase52Result.blocked(
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
            reason="REAL XAUUSD DATA REQUIRED (insufficient bars)",
        )
    missing_required = [
        s
        for s in cfg.required_macro_symbols
        if s not in macro_factor_series or len(macro_factor_series[s]) != len(close)
    ]
    if missing_required:
        return Phase52Result.blocked(
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
            reason=f"REQUIRED MACRO DATA MISSING OR MISALIGNED: {', '.join(missing_required)}",
            macro_symbols_missing=tuple(missing_required),
        )

    input_provenance = build_input_provenance(
        target_timestamps,
        close,
        high,
        low,
        volume,
        macro_timestamps,
        macro_factor_series,
        cfg.required_macro_symbols,
    )
    dataset, macro_diag = build_macro_augmented_dataset(
        close, high, low, volume, macro_factor_series, cfg.horizon, cfg.threshold
    )
    if dataset.sample_count < cfg.train_size + cfg.validation_size:
        return Phase52Result.blocked(
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
            reason="REAL XAUUSD + MACRO DATA REQUIRED (insufficient aligned samples after merge)",
            macro_symbols_present=macro_diag.symbols_present,
            macro_symbols_missing=macro_diag.symbols_missing,
        )

    feat, labs, names = dataset.features, dataset.labels, dataset.feature_names
    source_indices = list(dataset.metadata["source_indices"])
    try:
        feature_indices = _resolve_feature_indices(cfg, names, dict(dataset.metadata))
    except ValueError as exc:
        return Phase52Result.blocked(
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
            reason=str(exc),
            macro_symbols_present=macro_diag.symbols_present,
            macro_symbols_missing=macro_diag.symbols_missing,
        )
    all_model_preds: list[int] = []
    all_base_preds: list[int] = []
    all_actuals: list[float] = []
    all_probs: list[dict[int, float]] = []
    all_close_at_val: list[float] = []
    train_size, val_size, step = cfg.train_size, cfg.validation_size, cfg.step_size
    folds, start = 0, 0
    close_list = list(close)
    while start + train_size + val_size <= len(feat):
        tr_feat, tr_lab = feat[start : start + train_size], labs[start : start + train_size]
        val_start = start + train_size
        val_feat, val_lab = (
            feat[val_start : val_start + val_size],
            labs[val_start : val_start + val_size],
        )
        val_source_indices = source_indices[val_start : val_start + val_size]
        if cfg.estimator_feature is not None:
            est: EmpiricalProbabilityEstimator | MultivariateEmpiricalProbabilityEstimator = EmpiricalProbabilityEstimator(
                n_bins=cfg.n_bins, feature_indices=feature_indices
            ).fit(tr_feat, tr_lab)
        else:
            est = MultivariateEmpiricalProbabilityEstimator(
                feature_indices=feature_indices, n_neighbors=cfg.n_neighbors
            ).fit(tr_feat, tr_lab)
        base_pred = baseline_always_predict(tr_lab, val_lab)
        _, preds, probs = _evaluate_model(est, val_feat, val_lab)
        all_model_preds.extend(preds)
        all_base_preds.extend([int(base_pred)] * len(val_lab))
        all_actuals.extend(val_lab)
        all_probs.extend(probs)
        all_close_at_val.extend(close_list[i] for i in val_source_indices)
        folds += 1
        start += step
        if step <= 0:
            break

    if folds == 0:
        return Phase52Result.blocked(
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
            reason="No walk-forward folds could be formed",
            macro_symbols_present=macro_diag.symbols_present,
            macro_symbols_missing=macro_diag.symbols_missing,
        )
    baseline = _baseline_like(all_base_preds, all_actuals)
    model = _model_like(all_model_preds, all_actuals, all_probs)
    cost = apply_costs(
        all_model_preds,
        all_actuals,
        all_close_at_val,
        cfg.threshold,
        spread_spec=cfg.spread_spec,
        slippage_spec=cfg.slippage_spec,
        commission_spec=cfg.commission_spec,
        cost_applied=cfg.cost_applied,
    )
    calibration = evaluate_calibration(
        all_probs,
        all_actuals,
        num_bins=cfg.n_bins,
        model_brier=model.brier_score,
        baseline_brier=baseline.brier_score,
        baseline=baseline,
    )
    significance = evaluate_significance(
        all_model_preds, all_base_preds, all_actuals, cfg.significance_level
    )
    flags = aggregate_outcome(
        data_valid=True,
        leakage_check=True,
        out_of_sample=True,
        cost_adjusted=cfg.cost_applied,
        reproducible=True,
        model_accuracy=model.accuracy,
        baseline_accuracy=baseline.accuracy,
        net_accuracy_all=cost.net_accuracy_all,
        significant=significance.significant,
        min_sample_count=cfg.min_sample_count,
        validation_sample_count=len(all_actuals),
        brier_model=model.brier_score,
        brier_baseline=baseline.brier_score,
    )
    metadata = {
        "phase52_version": "1.2.0",
        "framework": "researchos.experiments.phase52",
        "feature_set": cfg.feature_set,
        "selected_feature_indices": list(feature_indices),
        "selected_feature_names": [names[i] for i in feature_indices],
        "num_folds": folds,
        "feature_count": len(names),
        "price_feature_count": dataset.metadata.get("price_feature_count"),
        "macro_feature_count": dataset.metadata.get("macro_feature_count"),
        "estimator": "EmpiricalProbabilityEstimator"
        if cfg.estimator_feature is not None
        else "MultivariateEmpiricalProbabilityEstimator",
        "n_neighbors": cfg.n_neighbors if cfg.estimator_feature is None else None,
        "baseline": "unconditional-frequency majority",
        "symbol": cfg.symbol,
        "timeframe": cfg.timeframe,
        "horizon": cfg.horizon,
        "threshold": cfg.threshold,
        "timestamp_contract": "exact_utc_one_to_one_order_preserving",
        "source_index_contract": "retained_dataset_row_to_original_ohlcv_row",
        "input_provenance": input_provenance,
    }
    return Phase52Result(
        outcome=flags.outcome,
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
        horizon=cfg.horizon,
        threshold=cfg.threshold,
        train_size=train_size,
        validation_size=val_size,
        step_size=step,
        num_folds=folds,
        macro_symbols_present=macro_diag.symbols_present,
        macro_symbols_missing=macro_diag.symbols_missing,
        estimator_feature_name=names[feature_indices[0]],
        baseline=baseline,
        model=model,
        cost=cost,
        calibration=calibration,
        significance=significance,
        validation=flags,
        metadata=metadata,
    )


def run_phase52_comparison(
    *args, config: Phase52Config | None = None, **kwargs
) -> dict[str, Phase52Result]:
    """Run all five feature sets with identical data, labels, folds and costs."""
    base = config or Phase52Config()
    kwargs_without_config = dict(kwargs)
    kwargs_without_config.pop("config", None)
    return {
        feature_set: run_phase52(*args, config=replace(base, feature_set=feature_set), **kwargs_without_config)
        for feature_set in FEATURE_SET_NAMES
    }


__all__ = ["FEATURE_SET_NAMES", "Phase52Config", "run_phase52", "run_phase52_comparison"]
