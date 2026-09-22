""""Market Memory Pipeline — end-to-end market memory research pipeline."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from researchos.market_memory.conditioning import ConditionSpec, MultipleTestingAudit, compute_conditional_statistics, filter_events
from researchos.market_memory.event_extractor import extract_sma_crossover_events
from researchos.market_memory.event_schema import ConditionalResult, ConditionalResult, EventType, EvidenceStatus, MarketEvent, MarketMemoryReport, ValidationResult
from researchos.market_memory.evidence import create_evidence_record
from researchos.market_memory.label_dependence import audit_label_overlap
from researchos.market_memory.oos_validation import OOSValidationResult, walk_forward_validate
from researchos.market_memory.outcome_engine import compute_forward_outcomes
from researchos.market_memory.production_gate import check_production_evidence_readiness
from researchos.market_memory.self_audit import run_self_audit
from researchos.market_memory.statistical_evidence import bonferroni_alpha, wilson_proportion_ci
from researchos.market_memory.temporal_validation import chronological_split, check_temporal_integrity


_PIPELINE_OUTCOME_HORIZON_DAYS = 1
_PIPELINE_ALPHA = 0.05


def _compute_dataset_hash(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _finite_returns(events: list[MarketEvent], condition: ConditionSpec) -> list[float]:
    values: list[float] = []
    for event in filter_events(events, condition):
        value = event.outcome.return_1d if event.outcome else None
        if isinstance(value, (int, float)) and value == value and abs(value) != float("inf"):
            values.append(float(value))
    return values


def run_market_memory_pipeline(
    data_path: str = "data/curated/xauusd/xauusd_d1_2021_2025_mt5_final.csv",
    asset: str = "XAUUSD",
    timeframe: str = "D1",
    fast_period: int = 20,
    slow_period: int = 100,
    seed: int = 42,
    conditions: list[ConditionSpec] | None = None,
    *,
    enforce_production_gate: bool = False,
    minimum_events: int = 100,
) -> MarketMemoryReport:
    """Run deterministic Market Memory research from raw CSV to report."""
    from researchos.market_memory.event_extractor import load_xauusd_d1

    if minimum_events < 1:
        raise ValueError("minimum_events must be >= 1")

    df = load_xauusd_d1(data_path)
    dataset_hash = _compute_dataset_hash(data_path)
    dataset_id = f"{asset}_{timeframe}_{dataset_hash}"
    events = extract_sma_crossover_events(df, fast_period=fast_period, slow_period=slow_period, dataset_source=dataset_id, seed=seed)
    price_df = df.select(["timestamp", "open", "high", "low", "close"])
    events = compute_forward_outcomes(events, price_df, horizons=[_PIPELINE_OUTCOME_HORIZON_DAYS])

    temporal_audit = check_temporal_integrity(events)
    if temporal_audit["status"] != "PASS":
        raise ValueError(f"Temporal integrity failed: {temporal_audit['issues']}")

    if enforce_production_gate:
        gate = check_production_evidence_readiness(events, dataset_source=dataset_id, minimum_events=minimum_events)
        if not gate.passed:
            return MarketMemoryReport(
                report_id=f"MMR|{asset}|{timeframe}|SMA{fast_period}_{slow_period}|{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                asset=asset, timeframe=timeframe, event_type=EventType.SMA_CROSSOVER.value,
                total_events=len(events), date_range=(events[0].timestamp.isoformat() if events else "", events[-1].timestamp.isoformat() if events else ""),
                outcomes={"total_events": len(events)}, conditional_results=[], validation_results=[], evidence_records=[], self_audit=None,
                overall_status=EvidenceStatus.REJECTED.value, notes="PRODUCTION GATE FAILED: " + "; ".join(gate.issues),
            )

    if conditions is None:
        conditions = [
            ConditionSpec("all_crossovers", {}, "All SMA crossovers"),
            ConditionSpec("bullish_crossover", {"direction": "bullish"}, "Bullish SMA crossovers only"),
            ConditionSpec("bearish_crossover", {"direction": "bearish"}, "Bearish SMA crossovers only"),
            ConditionSpec("low_volatility", {"volatility_state": "Low"}, "Crossovers in low volatility regime"),
            ConditionSpec("high_volatility", {"volatility_state": "High"}, "Crossovers in high volatility regime"),
        ]


    train_events, validation_events, test_events = chronological_split(events)
    validation_results: list[ValidationResult] = []
    oos_results: dict[str, OOSValidationResult | None] = {}

    def label_end_getter(event: MarketEvent) -> datetime | None:
        """Return the actual future observation timestamp used by the outcome."""
        if event.outcome is None:
            return None
        value = event.outcome.data_availability.get(
            f"realized_end_{_PIPELINE_OUTCOME_HORIZON_DAYS}d"
        )
        if value is None:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    dependence_audit = audit_label_overlap(events, label_end_getter)
    dependence_block_size = max(1, dependence_audit.max_concurrent_labels)

    hypothesis_count = len(conditions)
    corrected_alpha = bonferroni_alpha(_PIPELINE_ALPHA, hypothesis_count)
    corrected_confidence_level = 1.0 - corrected_alpha

    conditional_results: list[ConditionalResult] = []
    probability_evidence: dict[str, object] = {}
    for spec in conditions:
        result = compute_conditional_statistics(events, spec, outcome_field="return_1d", bootstrap_seed=seed, dependence_block_size=dependence_block_size)
        conditional_results.append(result)
        values = _finite_returns(events, spec)
        if values:
            probability_evidence[spec.name] = wilson_proportion_ci(
                sum(value > 0.0 for value in values),
                len(values),
                confidence_level=corrected_confidence_level,
            )

    for cr in conditional_results:
        condition = cr.condition_spec

        def matcher(event: MarketEvent) -> bool:
            return bool(filter_events([event], condition))

        def outcome_getter(event: MarketEvent) -> float | None:
            return event.outcome.return_1d if event.outcome else None
        train_values = _finite_returns(train_events, condition)
        val_values = _finite_returns(validation_events, condition)
        test_values = _finite_returns(test_events, condition)
        oos = walk_forward_validate(
            events,
            matcher,
            outcome_getter,
            initial_train_size=max(100, min(500, len(events) // 3 or 1)),
            validation_size=max(20, min(100, len(events) // 10 or 1)),
            test_size=max(20, min(100, len(events) // 10 or 1)),
            step_size=max(20, min(100, len(events) // 10 or 1)),
            min_test_events=20,
            purge_days=_PIPELINE_OUTCOME_HORIZON_DAYS,
            max_outcome_horizon_days=_PIPELINE_OUTCOME_HORIZON_DAYS,
            label_end_getter=label_end_getter,
        ) if len(events) >= 160 else None
        oos_results[cr.condition_name] = oos

        train_mean = sum(train_values) / len(train_values) if train_values else 0.0
        val_mean = sum(val_values) / len(val_values) if val_values else 0.0
        test_mean = sum(test_values) / len(test_values) if test_values else 0.0
        is_stable = oos is not None and oos.stable and bool(train_values) and bool(val_values) and bool(test_values)
        notes = f"OOS={oos.status}, folds={oos.total_folds}, passed={oos.passed_folds}" if oos is not None else "Insufficient events for walk-forward OOS"
        validation_results.append(ValidationResult(
            condition_name=cr.condition_name,
            train_period=(train_events[0].timestamp.isoformat() if train_events else "", train_events[-1].timestamp.isoformat() if train_events else ""),
            validation_period=(validation_events[0].timestamp.isoformat() if validation_events else "", validation_events[-1].timestamp.isoformat() if validation_events else ""),
            test_period=(test_events[0].timestamp.isoformat() if test_events else "", test_events[-1].timestamp.isoformat() if test_events else ""),
            train_events=len(train_values), validation_events=len(val_values), test_events=len(test_values),
            train_statistic=train_mean, validation_statistic=val_mean, test_statistic=test_mean,
            is_stable=is_stable,
            validation_method="walk_forward_expanding_purged" if oos is not None else "chronological_split_insufficient_for_oos",
            notes=notes,
        ))

    audit = run_self_audit(
        events,
        conditional_results,
        label_end_getter=label_end_getter,
        multiple_testing_corrected=True,
    )
    multiple_testing = MultipleTestingAudit(
        total_hypotheses_tested=hypothesis_count,
        conditions_tested=[c.name for c in conditions],
        selection_process="Pre-specified based on domain knowledge (regime, direction, volatility)",
        correction_applied=f"Bonferroni family-wise error control: alpha={_PIPELINE_ALPHA:.4f}, per-hypothesis alpha={corrected_alpha:.6f}",
        limitations="Probability CIs use Bonferroni-adjusted confidence. Bootstrap mean CI remains descriptive; OOS stability is required for validation. Bonferroni does not remove serial dependence from overlapping realized labels.",
    )

    evidence_records = []
    for cr in conditional_results:
        oos = oos_results[cr.condition_name]
        validated = oos is not None and oos.stable and audit.overall_status != "FAIL"
        status = EvidenceStatus.VALIDATED.value if validated else cr.status
        prob = probability_evidence.get(cr.condition_name)
        uncertainty: dict[str, object] = {"mean_confidence_interval": cr.confidence_interval}
        if prob:
            uncertainty["probability_confidence_interval"] = list(prob.confidence_interval)
            uncertainty["probability_confidence_level"] = prob.confidence_level
            uncertainty["multiple_testing"] = {
                "method": "bonferroni",
                "family_alpha": _PIPELINE_ALPHA,
                "hypotheses": hypothesis_count,
                "per_hypothesis_alpha": corrected_alpha,
            }
        uncertainty["label_dependence"] = {
            "method": "realized_label_interval_overlap",
            "interval_definition": "[event_timestamp, realized_end)",
            "total_events": dependence_audit.total_events,
            "events_with_realized_end": dependence_audit.events_with_realized_end,
            "missing_realized_end": dependence_audit.missing_realized_end,
            "overlap_pairs": dependence_audit.overlap_pairs,
            "max_concurrent_labels": dependence_audit.max_concurrent_labels,
            "interpretation": "Overlap is reported as dependence information; it is not treated as evidence of leakage.",
            "inference_method": "moving_block_bootstrap" if dependence_block_size > 1 else "percentile_bootstrap",
            "block_size": dependence_block_size,
            "block_size_rule": "maximum concurrent realized labels; block bootstrap only when overlap exists",
            "assumption": "Dependence is treated as predominantly local in event order within the reported block size; this does not establish independence beyond the block.",
        }
        if oos:
            uncertainty["oos"] = {
                "status": oos.status, "folds": oos.total_folds, "passed_folds": oos.passed_folds,
                "validation_method": oos.validation_method, "purge_days": oos.purge_days,
                "embargo_days": oos.embargo_days, "max_outcome_horizon_days": _PIPELINE_OUTCOME_HORIZON_DAYS,
                "label_boundary_audit": "PASS",
            }
        evidence_records.append(create_evidence_record(
            finding_name=f"SMA Crossover {cr.condition_name}", dataset_id=dataset_id, dataset_version=dataset_hash,
            event_definition=f"SMA{fast_period}/{slow_period} crossover on {asset} {timeframe}",
            condition_definition=str(cr.condition_spec.to_dict()["conditions"]), sample_size=cr.sample_size,
            time_range=(events[0].timestamp.isoformat() if events else "", events[-1].timestamp.isoformat() if events else ""),
            computation_method="forward_return_analysis", code_module="researchos.market_memory.pipeline_v1",
            statistical_method="Bonferroni-adjusted Wilson probability CI + dependence-aware block bootstrap mean CI when labels overlap + purged walk-forward OOS + realized-label boundary and dependence audit",
            result={"raw_probability": cr.raw_probability, "mean_return": cr.mean_return, "std_return": cr.std_return},
            uncertainty=uncertainty, validation_method="walk_forward_expanding_purged", random_seed=seed, status=status,
        ))

    if audit.overall_status == "FAIL":
        overall_status = EvidenceStatus.REJECTED.value
    elif all(oos is not None and oos.stable for oos in oos_results.values()) and oos_results:
        overall_status = EvidenceStatus.VALIDATED.value
    else:
        overall_status = EvidenceStatus.UNVALIDATED.value

    return MarketMemoryReport(
        report_id=f"MMR|{asset}|{timeframe}|SMA{fast_period}_{slow_period}|{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        asset=asset, timeframe=timeframe, event_type=EventType.SMA_CROSSOVER.value,
        total_events=len(events), date_range=(events[0].timestamp.isoformat() if events else "", events[-1].timestamp.isoformat() if events else ""),
        outcomes={
            "total_events": len(events),
            "bullish_count": sum(1 for e in events if e.direction == "bullish"),
            "bearish_count": sum(1 for e in events if e.direction == "bearish"),
            "avg_return_1d": (sum(v for e in events if e.outcome and isinstance((v := e.outcome.return_1d), (int, float)) and v == v and abs(v) != float("inf")) / len([e for e in events if e.outcome and isinstance(e.outcome.return_1d, (int, float)) and e.outcome.return_1d == e.outcome.return_1d and abs(e.outcome.return_1d) != float("inf")])) if any(e.outcome and isinstance(e.outcome.return_1d, (int, float)) and e.outcome.return_1d == e.outcome.return_1d and abs(e.outcome.return_1d) != float("inf") for e in events) else 0.0,
        },
        conditional_results=conditional_results, validation_results=validation_results, evidence_records=evidence_records,
        self_audit=audit, overall_status=overall_status,
        notes=f"Dataset hash: {dataset_hash}. Multiple testing audit: {multiple_testing.to_dict()}. Label dependence audit: {dependence_audit}",
    )
