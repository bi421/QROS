"""Leakage-safe feature construction with pre-research context."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from researchos.experiments.phase52.macro_features import MacroFeatureBuilder
from researchos.quant_engine.machine_learning.features import FeatureBuilder
from researchos.quant_engine.machine_learning.labels import multiclass_label

from .daily_dataset import DailyObservation
from .feature_contract import FEATURE_SET_NAMES, Phase52FeatureContract, PRICE_FEATURE_NAMES
from .feature_dataset import FeatureDataset, _selected_macro_columns


@dataclass(frozen=True)
class ContextFeatureAudit:
    context_rows: int
    research_rows: int
    warmup_rows: int
    label_horizon: int
    emitted_rows: int
    expected_emitted_rows: int
    context_sufficient: bool

    @property
    def invariant_ok(self) -> bool:
        return (
            self.context_sufficient
            and self.emitted_rows == self.expected_emitted_rows
            and self.emitted_rows == max(0, self.research_rows - self.label_horizon)
        )


def _validate_boundaries(
    context: tuple[DailyObservation, ...],
    research: tuple[DailyObservation, ...],
) -> None:
    if not research:
        raise ValueError("research observations cannot be empty")
    if context and context[-1].day >= research[0].day:
        raise ValueError("context must end strictly before research starts")
    combined = context + research
    days = [o.day for o in combined]
    if days != sorted(days) or len(days) != len(set(days)):
        raise ValueError("context + research observations must be unique and chronological")


def build_context_feature_dataset(
    context_observations: tuple[DailyObservation, ...],
    research_observations: tuple[DailyObservation, ...],
    feature_set: str,
    contract: Phase52FeatureContract | None = None,
) -> tuple[FeatureDataset, ContextFeatureAudit]:
    """Build research samples using pre-research context only for feature state."""
    contract = contract or Phase52FeatureContract()
    if feature_set not in FEATURE_SET_NAMES:
        raise ValueError(f"unsupported feature set: {feature_set}")
    _validate_boundaries(context_observations, research_observations)
    if len(context_observations) < contract.warmup:
        raise ValueError(
            f"context has {len(context_observations)} rows; "
            f"{contract.warmup} warm-up rows are required"
        )

    combined = context_observations + research_observations
    close = [o.close for o in combined]
    high = [o.high for o in combined]
    low = [o.low for o in combined]
    volume = [o.tick_volume for o in combined]
    vwap_values = [o.vwap for o in combined]
    price_features = FeatureBuilder(
        close,
        high,
        low,
        volume,
        vwap_values=vwap_values,
    ).build(drop_na=False)
    if tuple(price_features.feature_names) != PRICE_FEATURE_NAMES:
        raise AssertionError("frozen price feature contract changed unexpectedly")

    macro_factors = {
        "DXY": [o.dxy for o in combined],
        "US10Y": [o.us10y for o in combined],
        "VIX": [o.vix for o in combined],
    }
    macro_set = MacroFeatureBuilder(
        aligned_length=len(combined), factor_series=macro_factors
    ).build()
    macro_names, macro_rows = _selected_macro_columns(
        macro_set.data, macro_set.feature_names, feature_set
    )
    combined_names = tuple(price_features.feature_names) + macro_names
    labels = multiclass_label(close, contract.horizon, contract.threshold)

    first_research_index = len(context_observations)
    rows: list[tuple[float, ...]] = []
    aligned_labels: list[int] = []
    source_days: list[str] = []
    prediction_timestamps: list[str] = []

    for i in range(first_research_index, len(combined)):
        row = tuple(price_features.data[i]) + tuple(macro_rows[i])
        if len(row) != len(combined_names):
            raise AssertionError("feature row shape mismatch")
        label = labels[i]
        if label is None:
            continue
        if any(v is None or (isinstance(v, float) and not math.isfinite(v)) for v in row):
            continue
        rows.append(tuple(float(v) for v in row))
        aligned_labels.append(int(label))
        day = combined[i].day
        source_days.append(day)
        dt = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
        prediction_timestamps.append((dt + timedelta(days=1)).isoformat().replace("+00:00", "Z"))

    expected = max(0, len(research_observations) - contract.horizon)
    audit = ContextFeatureAudit(
        context_rows=len(context_observations),
        research_rows=len(research_observations),
        warmup_rows=contract.warmup,
        label_horizon=contract.horizon,
        emitted_rows=len(rows),
        expected_emitted_rows=expected,
        context_sufficient=len(context_observations) >= contract.warmup,
    )
    if not audit.invariant_ok:
        raise AssertionError(
            "context feature accounting mismatch: " f"expected {expected}, got {len(rows)}"
        )

    metadata: dict[str, object] = {
        "feature_set": feature_set,
        "feature_names": list(combined_names),
        "feature_count": len(combined_names),
        "price_feature_count": len(price_features.feature_names),
        "context_rows": len(context_observations),
        "research_rows": len(research_observations),
        "warmup_rows": contract.warmup,
        "label_horizon": contract.horizon,
        "final_usable_rows": len(rows),
        "minimum_required_rows": contract.minimum_samples,
        "train_size": contract.train_size,
        "validation_size": contract.validation_size,
        "prediction_timing": contract.prediction_timing,
        "label_definition": contract.label_definition,
        "context_is_feature_state_only": True,
        "context_rows_emitted": False,
        "no_interpolation_or_forward_fill": True,
        "source_indices": list(range(len(rows))),
        "source_days": list(source_days),
        "prediction_timestamps": list(prediction_timestamps),
    }
    return FeatureDataset(
        feature_set=feature_set,
        feature_names=combined_names,
        rows=tuple(rows),
        labels=tuple(aligned_labels),
        source_days=tuple(source_days),
        prediction_timestamps=tuple(prediction_timestamps),
        metadata=metadata,
    ), audit


__all__ = ["ContextFeatureAudit", "build_context_feature_dataset"]
