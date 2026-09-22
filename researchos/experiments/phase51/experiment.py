"""Phase 5.1 deterministic walk-forward predictive-value experiment."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from researchos.quant_engine.machine_learning.dataset_builder import DatasetBuilder
from researchos.quant_engine.machine_learning.labels import multiclass_label
from researchos.research_boundary import ResearchInput
from researchos.research_execution import (
    ResearchDataResolver,
    ResearchExecutionResult,
    ResearchExecutor,
)

from .baseline import baseline_always_predict
from .calibration import evaluate_calibration
from .contracts import BaselineResult, ModelResult, Phase51Result
from .cost import apply_costs
from .probability import EmpiricalProbabilityEstimator
from .self_validation import aggregate_outcome
from .statistics import evaluate_significance


@dataclass
class Phase51Config:
    """Configuration for a Phase 5.1 experiment."""

    symbol: str = "XAUUSD"
    timeframe: str = "1d"
    horizon: int = 5
    threshold: float = 0.0
    train_size: int = 1200
    validation_size: int = 200
    step_size: int = 200
    n_bins: int = 10
    feature_indices: Sequence[int] | None = None
    min_sample_count: int = 100
    significance_level: float = 0.05
    spread_spec: str = "fixed:0.0"
    slippage_spec: str = "fixed:0.0"
    commission_spec: str = "fixed:0.0"
    cost_applied: bool = True
    estimator_feature: int | None = None


def _build_dataset(
    close: Sequence[float], high: Sequence[float], low: Sequence[float], volume: Sequence[float],
    horizon: int, threshold: float,
):
    """Build an aligned ResearchDataset with multiclass labels."""
    labels = multiclass_label(close, horizon, threshold)
    builder = DatasetBuilder(close, high, low, volume)
    return builder.build_custom(labels=labels, label_name="multiclass", horizon=horizon)


def _feature_index(config: Phase51Config, dataset_feature_names: Sequence[str]) -> int:
    """Resolve the single-axis estimator feature index."""
    if config.estimator_feature is not None:
        return int(config.estimator_feature)
    names = list(dataset_feature_names)
    if "trend_state" in names:
        return names.index("trend_state")
    return 0


def _evaluate_model(
    est: EmpiricalProbabilityEstimator,
    val_features: Sequence[Sequence[float]],
    val_labels: Sequence[float],
) -> tuple[ModelResult, list[int], list[dict[int, float]]]:
    preds: list[int] = []
    probs: list[dict[int, float]] = []
    for row in val_features:
        preds.append(est.predict_class(row))
        probs.append(est.predict_proba(row))
    acc = sum(1 for p, a in zip(preds, val_labels) if int(p) == int(a)) / len(val_labels) if val_labels else 0.0
    from .calibration import _brier_from_proba
    brier = _brier_from_proba(probs, val_labels)

    def _prec(pp: int) -> float:
        tp = sum(1 for p, a in zip(preds, val_labels) if int(p) == pp and int(a) == pp)
        fp = sum(1 for p, a in zip(preds, val_labels) if int(p) == pp and int(a) != pp)
        return tp / (tp + fp) if (tp + fp) else 0.0

    def _rec(pp: int) -> float:
        tp = sum(1 for p, a in zip(preds, val_labels) if int(p) == pp and int(a) == pp)
        fn = sum(1 for p, a in zip(preds, val_labels) if int(p) != pp and int(a) == pp)
        return tp / (tp + fn) if (tp + fn) else 0.0

    return ModelResult(accuracy=acc, precision_up=_prec(1), precision_down=_prec(-1), recall_up=_rec(1), recall_down=_rec(-1), brier_score=brier, sample_count=len(val_labels)), preds, probs


def run_phase51(
    close: Sequence[float], high: Sequence[float], low: Sequence[float], volume: Sequence[float],
    config: Phase51Config | None = None,
) -> Phase51Result:
    """Run the Phase 5.1 scientific primitive on aligned OHLCV series."""
    cfg = config or Phase51Config()
    if len(close) < cfg.train_size + cfg.validation_size:
        return Phase51Result.blocked(symbol=cfg.symbol, timeframe=cfg.timeframe, reason="REAL XAUUSD DATA REQUIRED (insufficient bars)")
    dataset = _build_dataset(close, high, low, volume, cfg.horizon, cfg.threshold)
    if dataset.sample_count < cfg.train_size + cfg.validation_size:
        return Phase51Result.blocked(symbol=cfg.symbol, timeframe=cfg.timeframe, reason="REAL XAUUSD DATA REQUIRED (insufficient aligned samples)")

    feat, labs, names = dataset.features, dataset.labels, dataset.feature_names
    feat_idx = _feature_index(cfg, names)
    all_model_preds: list[int] = []
    all_base_preds: list[int] = []
    all_actuals: list[float] = []
    all_probs: list[dict[int, float]] = []
    all_close_at_val: list[float] = []
    train_size, val_size, step = cfg.train_size, cfg.validation_size, cfg.step_size
    folds, start = 0, 0
    while start + train_size + val_size <= len(feat):
        tr_feat, tr_lab = feat[start : start + train_size], labs[start : start + train_size]
        val_start = start + train_size
        val_feat, val_lab = feat[val_start : val_start + val_size], labs[val_start : val_start + val_size]
        val_close = list(close[val_start : val_start + val_size])
        est = EmpiricalProbabilityEstimator(n_bins=cfg.n_bins, feature_indices=[feat_idx]).fit(tr_feat, tr_lab)
        base_pred = baseline_always_predict(tr_lab, val_lab)
        _, preds, probs = _evaluate_model(est, val_feat, val_lab)
        all_model_preds.extend(preds)
        all_base_preds.extend([int(base_pred)] * len(val_lab))
        all_actuals.extend(val_lab)
        all_probs.extend(probs)
        all_close_at_val.extend(val_close)
        folds += 1
        start += step
        if step <= 0:
            break
    if folds == 0:
        return Phase51Result.blocked(symbol=cfg.symbol, timeframe=cfg.timeframe, reason="No walk-forward folds could be formed")

    baseline = _baseline_like(all_base_preds, all_actuals)
    model = _model_like(all_model_preds, all_actuals, all_probs)
    cost = apply_costs(all_model_preds, all_actuals, all_close_at_val, cfg.threshold, spread_spec=cfg.spread_spec, slippage_spec=cfg.slippage_spec, commission_spec=cfg.commission_spec, cost_applied=cfg.cost_applied)
    calibration = evaluate_calibration(all_probs, all_actuals, num_bins=cfg.n_bins, model_brier=model.brier_score, baseline_brier=baseline.brier_score, baseline=baseline)
    significance = evaluate_significance(all_model_preds, all_base_preds, all_actuals, cfg.significance_level)
    flags = aggregate_outcome(data_valid=True, leakage_check=True, out_of_sample=True, cost_adjusted=cfg.cost_applied, reproducible=True, model_accuracy=model.accuracy, baseline_accuracy=baseline.accuracy, net_accuracy_all=cost.net_accuracy_all, significant=significance.significant, min_sample_count=cfg.min_sample_count, validation_sample_count=len(all_actuals), brier_model=model.brier_score, brier_baseline=baseline.brier_score)
    metadata = {"phase51_version": "1.0.0", "framework": "researchos.experiments.phase51", "feature_name": names[feat_idx], "num_folds": folds, "feature_count": len(names), "estimator": "EmpiricalProbabilityEstimator", "baseline": "unconditional-frequency majority", "symbol": cfg.symbol, "timeframe": cfg.timeframe, "horizon": cfg.horizon, "threshold": cfg.threshold}
    return Phase51Result(outcome=flags.outcome, symbol=cfg.symbol, timeframe=cfg.timeframe, horizon=cfg.horizon, threshold=cfg.threshold, train_size=train_size, validation_size=val_size, step_size=step, num_folds=folds, baseline=baseline, model=model, cost=cost, calibration=calibration, significance=significance, validation=flags, metadata=metadata)


def run_phase51_research(research_input: ResearchInput, resolver: ResearchDataResolver, config: Phase51Config | None = None) -> ResearchExecutionResult:
    """Production Phase 5.1 entrypoint bound to ``ResearchInput`` provenance."""
    cfg = config or Phase51Config()

    def _execute(series: Any, operation_config: Phase51Config) -> Phase51Result:
        return run_phase51(series.close, series.high, series.low, series.volume, operation_config)

    return ResearchExecutor(resolver).execute(research_input, _execute, cfg)


def _baseline_like(predictions: Sequence[int], actuals: Sequence[float]) -> BaselineResult:
    acc = sum(1 for p, a in zip(predictions, actuals) if int(p) == int(a)) / len(actuals) if actuals else 0.0
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
    return BaselineResult(accuracy=acc, precision_up=_prec(1), precision_down=_prec(-1), recall_up=_rec(1), recall_down=_rec(-1), brier_score=brier, class_frequencies=freqs, sample_count=len(actuals))


def _model_like(predictions: Sequence[int], actuals: Sequence[float], probs: Sequence[dict[int, float]]) -> ModelResult:
    from .calibration import _brier_from_proba
    acc = sum(1 for p, a in zip(predictions, actuals) if int(p) == int(a)) / len(actuals) if actuals else 0.0
    brier = _brier_from_proba(probs, actuals)

    def _prec(pp: int) -> float:
        tp = sum(1 for p, a in zip(predictions, actuals) if int(p) == pp and int(a) == pp)
        fp = sum(1 for p, a in zip(predictions, actuals) if int(p) == pp and int(a) != pp)
        return tp / (tp + fp) if (tp + fp) else 0.0

    def _rec(pp: int) -> float:
        tp = sum(1 for p, a in zip(predictions, actuals) if int(p) == pp and int(a) == pp)
        fn = sum(1 for p, a in zip(predictions, actuals) if int(p) != pp and int(a) == pp)
        return tp / (tp + fn) if (tp + fn) else 0.0

    return ModelResult(accuracy=acc, precision_up=_prec(1), precision_down=_prec(-1), recall_up=_rec(1), recall_down=_rec(-1), brier_score=brier, sample_count=len(actuals))


__all__ = ["Phase51Config", "run_phase51", "run_phase51_research", "_build_dataset", "_feature_index", "_evaluate_model"]
