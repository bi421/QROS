"""Execution layer for prepared Phase 5.2 inputs.

This module deliberately separates expensive data preparation from the five
feature-set experiments. A canonical report prepares the dataset once, then
all feature sets consume the same immutable observations, labels and folds.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from researchos.experiments.phase51.baseline import baseline_always_predict
from researchos.experiments.phase51.calibration import _brier_from_proba, evaluate_calibration
from researchos.experiments.phase51.cost import apply_costs
from researchos.experiments.phase51.probability import EmpiricalProbabilityEstimator
from researchos.experiments.phase51.self_validation import aggregate_outcome
from researchos.experiments.phase51.statistics import evaluate_significance

from .contracts import BaselineResult, ModelResult, Phase52Result
from .experiment import FEATURE_SET_NAMES, Phase52Config, _resolve_feature_indices
from .multivariate import MultivariateEmpiricalProbabilityEstimator
from .prepared import Phase52PreparedData


def _model_eval(
    estimator: Any, features, labels
) -> tuple[ModelResult, list[int], list[dict[int, float]]]:
    predictions: list[int] = []
    probabilities: list[dict[int, float]] = []
    for row in features:
        row_probs = estimator.predict_proba(row)
        probabilities.append(row_probs)
        predictions.append(max((1, 0, -1), key=lambda cls: row_probs[cls]))
    accuracy = (
        sum(int(p) == int(a) for p, a in zip(predictions, labels)) / len(labels) if labels else 0.0
    )

    def precision(cls: int) -> float:
        tp = sum(int(p) == cls and int(a) == cls for p, a in zip(predictions, labels))
        fp = sum(int(p) == cls and int(a) != cls for p, a in zip(predictions, labels))
        return tp / (tp + fp) if tp + fp else 0.0

    def recall(cls: int) -> float:
        tp = sum(int(p) == cls and int(a) == cls for p, a in zip(predictions, labels))
        fn = sum(int(p) != cls and int(a) == cls for p, a in zip(predictions, labels))
        return tp / (tp + fn) if tp + fn else 0.0

    return (
        ModelResult(
            accuracy=accuracy,
            precision_up=precision(1),
            precision_down=precision(-1),
            recall_up=recall(1),
            recall_down=recall(-1),
            brier_score=_brier_from_proba(probabilities, labels),
            sample_count=len(labels),
        ),
        predictions,
        probabilities,
    )


def _baseline(predictions, actuals) -> BaselineResult:
    accuracy = (
        sum(int(p) == int(a) for p, a in zip(predictions, actuals)) / len(actuals)
        if actuals
        else 0.0
    )
    freqs = {"-1": 0.0, "0": 0.0, "1": 0.0}
    for actual in actuals:
        freqs[str(int(actual))] += 1.0
    total = sum(freqs.values()) or 1.0
    freqs = {key: value / total for key, value in freqs.items()}

    def precision(cls: int) -> float:
        tp = sum(int(p) == cls and int(a) == cls for p, a in zip(predictions, actuals))
        fp = sum(int(p) == cls and int(a) != cls for p, a in zip(predictions, actuals))
        return tp / (tp + fp) if tp + fp else 0.0

    def recall(cls: int) -> float:
        tp = sum(int(p) == cls and int(a) == cls for p, a in zip(predictions, actuals))
        fn = sum(int(p) != cls and int(a) == cls for p, a in zip(predictions, actuals))
        return tp / (tp + fn) if tp + fn else 0.0

    brier = 0.0
    for prediction, actual in zip(predictions, actuals):
        predicted = [0.0, 0.0, 0.0]
        target = [0.0, 0.0, 0.0]
        predicted[int(prediction) + 1] = 1.0
        target[int(actual) + 1] = 1.0
        brier += sum((p - a) ** 2 for p, a in zip(predicted, target))
    brier = brier / len(actuals) / 3.0 if actuals else 0.0
    return BaselineResult(
        accuracy=accuracy,
        precision_up=precision(1),
        precision_down=precision(-1),
        recall_up=recall(1),
        recall_down=recall(-1),
        brier_score=brier,
        class_frequencies=freqs,
        sample_count=len(actuals),
    )


def _run_prepared(prepared: Phase52PreparedData, cfg: Phase52Config) -> Phase52Result:
    prepared.validate(cfg.required_macro_symbols)
    blocked = prepared.blocked_if_insufficient(cfg.train_size, cfg.validation_size)
    provenance = prepared.input_provenance
    if blocked is not None:
        return replace(
            blocked,
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
            metadata={
                **blocked.metadata,
                "prepared_sample_count": prepared.sample_count,
                "required_sample_count": cfg.train_size + cfg.validation_size,
                "combined_input_hash": provenance["combined_input_hash"],
                "price_input_hash": provenance["price_input_hash"],
                "macro_input_hashes": provenance["macro_input_hashes"],
            },
        )

    dataset = prepared.dataset
    names = dataset.feature_names
    feature_indices = _resolve_feature_indices(cfg, names, dict(dataset.metadata))
    features, labels, source_indices = dataset.features, dataset.labels, prepared.source_indices
    all_predictions: list[int] = []
    all_baseline_predictions: list[int] = []
    all_actuals: list[float] = []
    all_probabilities: list[dict[int, float]] = []
    all_close: list[float] = []
    folds = 0
    start = 0
    while start + cfg.train_size + cfg.validation_size <= len(features):
        train_end = start + cfg.train_size
        validation_end = train_end + cfg.validation_size
        train_features, train_labels = features[start:train_end], labels[start:train_end]
        validation_features, validation_labels = (
            features[train_end:validation_end],
            labels[train_end:validation_end],
        )
        validation_source_indices = source_indices[train_end:validation_end]
        if cfg.estimator_feature is not None:
            estimator = EmpiricalProbabilityEstimator(
                n_bins=cfg.n_bins, feature_indices=feature_indices
            ).fit(train_features, train_labels)
        else:
            estimator = MultivariateEmpiricalProbabilityEstimator(
                feature_indices=feature_indices, n_neighbors=cfg.n_neighbors
            ).fit(train_features, train_labels)
        baseline_prediction = baseline_always_predict(train_labels, validation_labels)
        _, predictions, probabilities = _model_eval(
            estimator, validation_features, validation_labels
        )
        all_predictions.extend(predictions)
        all_baseline_predictions.extend([int(baseline_prediction)] * len(validation_labels))
        all_actuals.extend(validation_labels)
        all_probabilities.extend(probabilities)
        all_close.extend(prepared.close[i] for i in validation_source_indices)
        folds += 1
        if cfg.step_size <= 0:
            break
        start += cfg.step_size
    if folds == 0:
        return Phase52Result.blocked(
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
            reason="No walk-forward folds could be formed",
            macro_symbols_present=prepared.macro_diagnostics.symbols_present,
            macro_symbols_missing=prepared.macro_diagnostics.symbols_missing,
        )

    baseline = _baseline(all_baseline_predictions, all_actuals)
    model = _model_eval_from_predictions(all_predictions, all_actuals, all_probabilities)
    cost = apply_costs(
        all_predictions,
        all_actuals,
        all_close,
        cfg.threshold,
        spread_spec=cfg.spread_spec,
        slippage_spec=cfg.slippage_spec,
        commission_spec=cfg.commission_spec,
        cost_applied=cfg.cost_applied,
    )
    calibration = evaluate_calibration(
        all_probabilities,
        all_actuals,
        num_bins=cfg.n_bins,
        model_brier=model.brier_score,
        baseline_brier=baseline.brier_score,
        baseline=baseline,
    )
    significance = evaluate_significance(
        all_predictions, all_baseline_predictions, all_actuals, cfg.significance_level
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
        "prepared_dataset_contract": "single_materialized_dataset_shared_across_feature_sets",
        "hash_algorithm": provenance["hash_algorithm"],
        "combined_input_hash": provenance["combined_input_hash"],
        "price_input_hash": provenance["price_input_hash"],
        "macro_input_hashes": provenance["macro_input_hashes"],
    }
    return Phase52Result(
        outcome=flags.outcome,
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
        horizon=cfg.horizon,
        threshold=cfg.threshold,
        train_size=cfg.train_size,
        validation_size=cfg.validation_size,
        step_size=cfg.step_size,
        num_folds=folds,
        macro_symbols_present=prepared.macro_diagnostics.symbols_present,
        macro_symbols_missing=prepared.macro_diagnostics.symbols_missing,
        estimator_feature_name=names[feature_indices[0]],
        baseline=baseline,
        model=model,
        cost=cost,
        calibration=calibration,
        significance=significance,
        validation=flags,
        metadata=metadata,
    )


def _model_eval_from_predictions(predictions, actuals, probabilities) -> ModelResult:
    def precision(cls: int) -> float:
        tp = sum(int(p) == cls and int(a) == cls for p, a in zip(predictions, actuals))
        fp = sum(int(p) == cls and int(a) != cls for p, a in zip(predictions, actuals))
        return tp / (tp + fp) if tp + fp else 0.0

    def recall(cls: int) -> float:
        tp = sum(int(p) == cls and int(a) == cls for p, a in zip(predictions, actuals))
        fn = sum(int(p) != cls and int(a) == cls for p, a in zip(predictions, actuals))
        return tp / (tp + fn) if tp + fn else 0.0

    accuracy = (
        sum(int(p) == int(a) for p, a in zip(predictions, actuals)) / len(actuals)
        if actuals
        else 0.0
    )
    return ModelResult(
        accuracy=accuracy,
        precision_up=precision(1),
        precision_down=precision(-1),
        recall_up=recall(1),
        recall_down=recall(-1),
        brier_score=_brier_from_proba(probabilities, actuals),
        sample_count=len(actuals),
    )


def run_prepared_phase52_comparison(
    prepared: Phase52PreparedData, config: Phase52Config
) -> dict[str, Phase52Result]:
    """Run every Phase 5.2 feature set against one prepared dataset."""
    prepared.validate(config.required_macro_symbols)
    return {
        feature_set: _run_prepared(prepared, replace(config, feature_set=feature_set))
        for feature_set in FEATURE_SET_NAMES
    }


__all__ = ["run_prepared_phase52_comparison"]
