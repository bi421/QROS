"""Execution layer for prepared Phase 5.2 inputs.

This module deliberately separates expensive data preparation from the five
feature-set experiments. A canonical report prepares the dataset once, then
all feature sets consume the same immutable observations, labels and folds.
"""

from __future__ import annotations

from dataclasses import replace
from collections.abc import Sequence
from researchos.experiments.phase51.baseline import baseline_always_predict
from researchos.experiments.phase51.calibration import _brier_from_proba, evaluate_calibration
from researchos.experiments.phase51.cost import apply_costs
from researchos.experiments.phase51.probability import EmpiricalProbabilityEstimator
from researchos.experiments.phase51.self_validation import aggregate_outcome
from researchos.experiments.phase51.contracts import reproducibility_hash
from researchos.experiments.phase51.statistics import (
    confidence_interval_diff,
    evaluate_significance,
)
from researchos.orchestration.parallel import (
    ParallelResearchExecutor,
    ResearchBranch,
    ResearchWave,
)

from .contracts import BaselineResult, ModelResult, Phase52Result
from .experiment import FEATURE_SET_NAMES, Phase52Config, _resolve_feature_indices
from .multivariate import MultivariateEmpiricalProbabilityEstimator
from .prepared import Phase52PreparedData


def _model_eval(
    estimator: EmpiricalProbabilityEstimator | MultivariateEmpiricalProbabilityEstimator,
    features: Sequence[Sequence[float]],
    labels: Sequence[float],
) -> tuple[ModelResult, list[int], list[dict[int, float]]]:
    if isinstance(estimator, MultivariateEmpiricalProbabilityEstimator):
        probabilities = estimator.predict_proba_batch(features)
    else:
        probabilities = [estimator.predict_proba(row) for row in features]
    predictions = [
        max((1, 0, -1), key=lambda cls: row_probs[cls])
        for row_probs in probabilities
    ]
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


def _baseline(predictions: Sequence[int], actuals: Sequence[float]) -> BaselineResult:
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
    if cfg.train_size <= 0 or cfg.validation_size <= 0 or cfg.step_size <= 0:
        raise ValueError("train_size, validation_size and step_size must be positive")
    if cfg.step_size < cfg.validation_size:
        raise ValueError(
            "step_size must be >= validation_size so OOS validation windows do not overlap"
        )
    if cfg.horizon <= 0:
        raise ValueError("horizon must be positive")
    if cfg.holdout_size <= 0:
        raise ValueError("holdout_size must be positive")

    required_samples = cfg.train_size + cfg.validation_size + cfg.holdout_size + cfg.horizon
    if prepared.sample_count < required_samples:
        blocked = Phase52Result.blocked(
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
            reason=(
                "REAL XAUUSD DATA REQUIRED; MACRO DATA REQUIRED (insufficient aligned samples "
                "for walk-forward plus independent final holdout)"
            ),
            macro_symbols_present=prepared.macro_diagnostics.symbols_present,
            macro_symbols_missing=prepared.macro_diagnostics.symbols_missing,
        )
        return replace(
            blocked,
            metadata={
                **blocked.metadata,
                "prepared_dataset_contract": "single_materialized_dataset_shared_across_feature_sets",
                "actual_prepared_samples": prepared.sample_count,
                "holdout_predictions_present": False,
                "holdout_metrics_present": False,
            },
        )

    provenance = prepared.input_provenance
    dataset = prepared.dataset
    names = dataset.feature_names
    feature_indices = _resolve_feature_indices(cfg, names, dict(dataset.metadata))
    features, labels, source_indices = dataset.features, dataset.labels, prepared.source_indices
    sample_timestamps = [prepared.timestamps[i] for i in source_indices]
    realized_end_timestamps = []
    for source_index in source_indices:
        realized_index = source_index + cfg.horizon
        if realized_index >= len(prepared.timestamps):
            raise ValueError("Phase 5.2 label realization timestamp is unavailable")
        realized_end_timestamps.append(prepared.timestamps[realized_index])

    def _timestamp(value: object):
        import pandas as pd

        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")
        return timestamp

    if any(
        _timestamp(current) <= _timestamp(previous)
        for previous, current in zip(sample_timestamps, sample_timestamps[1:])
    ):
        raise ValueError("Phase 5.2 sample timestamps must be strictly increasing")
    if any(
        _timestamp(realized) < _timestamp(observed)
        for observed, realized in zip(sample_timestamps, realized_end_timestamps)
    ):
        raise ValueError(
            "Phase 5.2 realized-end timestamps must not precede observation timestamps"
        )

    holdout_start_index = len(features) - cfg.holdout_size
    holdout_start = _timestamp(sample_timestamps[holdout_start_index])
    holdout_positions = list(range(holdout_start_index, len(features)))
    pre_holdout_positions = list(range(holdout_start_index))

    all_predictions: list[int] = []
    all_baseline_predictions: list[int] = []
    all_actuals: list[float] = []
    all_probabilities: list[dict[int, float]] = []
    all_close: list[float] = []
    fold_metadata: list[dict[str, object]] = []
    folds = 0
    start = 0
    while start + cfg.train_size + cfg.horizon + cfg.validation_size <= holdout_start_index:
        training_start_index = start
        training_end_index = start + cfg.train_size
        validation_start_index = training_end_index + cfg.horizon
        validation_end_index = validation_start_index + cfg.validation_size
        training_positions = list(range(training_start_index, training_end_index))
        validation_positions = list(range(validation_start_index, validation_end_index))
        validation_start = _timestamp(sample_timestamps[validation_start_index])
        validation_end = _timestamp(sample_timestamps[validation_end_index - 1])
        validation_realized_end = max(
            _timestamp(realized_end_timestamps[position]) for position in validation_positions
        )
        if validation_realized_end >= holdout_start:
            break

        if any(
            _timestamp(realized_end_timestamps[position]) >= validation_start
            for position in training_positions
        ):
            raise RuntimeError("Validation training window violates realized-end embargo")
        training_features = [features[position] for position in training_positions]
        training_labels = [labels[position] for position in training_positions]
        validation_features = [features[position] for position in validation_positions]
        validation_labels = [labels[position] for position in validation_positions]

        if cfg.estimator_feature is not None:
            estimator: EmpiricalProbabilityEstimator | MultivariateEmpiricalProbabilityEstimator = EmpiricalProbabilityEstimator(
                n_bins=cfg.n_bins, feature_indices=feature_indices
            ).fit(training_features, training_labels)
        else:
            estimator = MultivariateEmpiricalProbabilityEstimator(
                feature_indices=feature_indices, n_neighbors=cfg.n_neighbors
            ).fit(training_features, training_labels)

        baseline_prediction = baseline_always_predict(training_labels, [])
        _, predictions, probabilities = _model_eval(
            estimator, validation_features, validation_labels
        )
        all_predictions.extend(predictions)
        all_baseline_predictions.extend([int(baseline_prediction)] * len(validation_labels))
        all_actuals.extend(validation_labels)
        all_probabilities.extend(probabilities)
        all_close.extend(
            prepared.close[source_indices[position]] for position in validation_positions
        )

        training_start = _timestamp(sample_timestamps[training_positions[0]])
        training_end = _timestamp(sample_timestamps[training_positions[-1]])
        training_realized_end = max(
            _timestamp(realized_end_timestamps[position]) for position in training_positions
        )
        fold_metadata.append(
            {
                "fold": folds + 1,
                "training_start": training_start.isoformat(),
                "training_end": training_end.isoformat(),
                "training_sample_count": len(training_positions),
                "training_max_realized_end": training_realized_end.isoformat(),
                "embargoed_observation_count": cfg.horizon,
                "validation_start": validation_start.isoformat(),
                "validation_end": validation_end.isoformat(),
                "validation_realized_end": validation_realized_end.isoformat(),
                "validation_sample_count": len(validation_positions),
                "embargo_rule": "realized_end < validation_start",
            }
        )
        folds += 1
        start += cfg.step_size

    if folds == 0:
        blocked = Phase52Result.blocked(
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
            reason="No leakage-safe walk-forward folds were produced before the final holdout",
            macro_symbols_present=prepared.macro_diagnostics.symbols_present,
            macro_symbols_missing=prepared.macro_diagnostics.symbols_missing,
        )
        return replace(
            blocked,
            metadata={
                **blocked.metadata,
                "prepared_dataset_contract": "single_materialized_dataset_shared_across_feature_sets",
                "actual_prepared_samples": prepared.sample_count,
                "holdout_predictions_present": False,
                "holdout_metrics_present": False,
            },
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

    holdout_training_positions = [
        position
        for position in pre_holdout_positions
        if _timestamp(realized_end_timestamps[position]) < holdout_start
    ]
    if len(holdout_training_positions) < cfg.train_size:
        raise RuntimeError("Insufficient leakage-safe training observations for final holdout")
    holdout_training_features = [features[position] for position in holdout_training_positions]
    holdout_training_labels = [labels[position] for position in holdout_training_positions]
    holdout_features = [features[position] for position in holdout_positions]
    holdout_labels = [labels[position] for position in holdout_positions]

    if cfg.estimator_feature is not None:
        holdout_estimator = EmpiricalProbabilityEstimator(
            n_bins=cfg.n_bins, feature_indices=feature_indices
        ).fit(holdout_training_features, holdout_training_labels)
    else:
        holdout_estimator = MultivariateEmpiricalProbabilityEstimator(
            feature_indices=feature_indices, n_neighbors=cfg.n_neighbors
        ).fit(holdout_training_features, holdout_training_labels)

    _, holdout_predictions, holdout_probabilities = _model_eval(
        holdout_estimator, holdout_features, holdout_labels
    )
    holdout_baseline_prediction = baseline_always_predict(holdout_training_labels, [])
    holdout_baseline_predictions = [holdout_baseline_prediction] * len(holdout_labels)
    holdout_model = _model_eval_from_predictions(
        holdout_predictions, holdout_labels, holdout_probabilities
    )
    holdout_baseline = _baseline(holdout_baseline_predictions, holdout_labels)
    holdout_close = [prepared.close[source_indices[position]] for position in holdout_positions]
    holdout_cost = apply_costs(
        holdout_predictions,
        holdout_labels,
        holdout_close,
        cfg.threshold,
        spread_spec=cfg.spread_spec,
        slippage_spec=cfg.slippage_spec,
        commission_spec=cfg.commission_spec,
        cost_applied=cfg.cost_applied,
    )
    holdout_significance = evaluate_significance(
        holdout_predictions,
        holdout_baseline_predictions,
        holdout_labels,
        cfg.significance_level,
    )
    holdout_accuracy_ci = confidence_interval_diff(
        [
            float(int(pred) == int(actual))
            for pred, actual in zip(holdout_predictions, holdout_labels)
        ],
        [
            float(int(pred) == int(actual))
            for pred, actual in zip(holdout_baseline_predictions, holdout_labels)
        ],
    )

    holdout_prediction_records = []
    for position, prediction, probability, label in zip(
        holdout_positions, holdout_predictions, holdout_probabilities, holdout_labels
    ):
        holdout_prediction_records.append(
            {
                "timestamp": _timestamp(sample_timestamps[position]).isoformat(),
                "realized_end": _timestamp(realized_end_timestamps[position]).isoformat(),
                "prediction": int(prediction),
                "probabilities": {
                    "-1": float(probability.get(-1, 0.0)),
                    "0": float(probability.get(0, 0.0)),
                    "1": float(probability.get(1, 0.0)),
                },
                "label": int(label),
            }
        )

    configuration = {
        "symbol": cfg.symbol,
        "timeframe": cfg.timeframe,
        "horizon": cfg.horizon,
        "threshold": cfg.threshold,
        "train_size": cfg.train_size,
        "validation_size": cfg.validation_size,
        "step_size": cfg.step_size,
        "holdout_size": cfg.holdout_size,
        "n_bins": cfg.n_bins,
        "min_sample_count": cfg.min_sample_count,
        "significance_level": cfg.significance_level,
        "spread_spec": cfg.spread_spec,
        "slippage_spec": cfg.slippage_spec,
        "commission_spec": cfg.commission_spec,
        "cost_applied": cfg.cost_applied,
        "estimator_feature": cfg.estimator_feature,
        "n_neighbors": cfg.n_neighbors,
        "required_macro_symbols": list(cfg.required_macro_symbols),
        "feature_set": cfg.feature_set,
    }

    metadata = {
        "phase52_version": "1.3.0",
        "framework": "researchos.experiments.phase52",
        "feature_set": cfg.feature_set,
        "selected_feature_indices": list(feature_indices),
        "selected_feature_names": [names[i] for i in feature_indices],
        "feature_set_search_scope": list(FEATURE_SET_NAMES),
        "feature_set_selection_policy": (
            "pre-registered five-way comparison; all feature sets are scored "
            "independently; final holdout results are not used for selection"
        ),
        "holdout_used_for_feature_selection": False,
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
        "configuration_hash": reproducibility_hash(configuration),
        "temporal_contract": {
            "feature_availability_convention": "observation_timestamp_after_source_bar_close",
            "label_definition": f"close[t+{cfg.horizon}] / close[t] - 1",
            "walk_forward_training_rule": "realized_end < validation_start",
            "final_holdout_training_rule": "realized_end < holdout_start",
            "holdout_is_chronologically_disjoint": True,
            "holdout_excluded_from_wfo_aggregate": True,
        },
        "wfo_folds": fold_metadata,
        "calibration_contract": {
            "method": "evaluation_only",
            "parameter_fitting_performed": False,
            "training_population": "walk-forward validation predictions only",
            "training_sample_count": len(all_actuals),
            "holdout_excluded": True,
            "holdout_sample_count_excluded": len(holdout_labels),
        },
        "holdout": {
            "start": _timestamp(sample_timestamps[holdout_positions[0]]).isoformat(),
            "end": _timestamp(sample_timestamps[holdout_positions[-1]]).isoformat(),
            "terminal_realized_end": _timestamp(
                realized_end_timestamps[holdout_positions[-1]]
            ).isoformat(),
            "holdout_events": len(holdout_positions),
            "pre_holdout_events": len(pre_holdout_positions),
            "training_events": len(holdout_training_positions),
            "training_start": _timestamp(
                sample_timestamps[holdout_training_positions[0]]
            ).isoformat(),
            "training_end": _timestamp(
                sample_timestamps[holdout_training_positions[-1]]
            ).isoformat(),
            "training_max_realized_end": max(
                _timestamp(realized_end_timestamps[position])
                for position in holdout_training_positions
            ).isoformat(),
            "fit_is_pre_holdout_only": True,
            "selection_frozen_before_scoring": True,
            "selection_scope": list(FEATURE_SET_NAMES),
            "holdout_used_for_selection": False,
            "prediction_count": len(holdout_prediction_records),
            "predictions": holdout_prediction_records,
            "baseline_prediction": int(holdout_baseline_prediction),
            "model": holdout_model.to_dict(),
            "baseline": holdout_baseline.to_dict(),
            "cost": holdout_cost.to_dict(),
            "significance": holdout_significance.to_dict(),
            "accuracy_delta_ci_95": {
                "lower": holdout_accuracy_ci[0],
                "upper": holdout_accuracy_ci[1],
            },
        },
    }

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


def _model_eval_from_predictions(
    predictions: Sequence[int],
    actuals: Sequence[float],
    probabilities: Sequence[dict[int, float]],
) -> ModelResult:
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
    branches = tuple(
        ResearchBranch(
            branch_id=feature_set,
            run=lambda _, feature_set=feature_set: _run_prepared(
                prepared, replace(config, feature_set=feature_set)
            ),
        )
        for feature_set in FEATURE_SET_NAMES
    )
    result = ParallelResearchExecutor(max_workers=len(branches)).run(
        (ResearchWave(wave_id="phase52-feature-sets", branches=branches),)
    )
    return result.by_branch_id()


__all__ = ["run_prepared_phase52_comparison"]
