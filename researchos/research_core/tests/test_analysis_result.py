from __future__ import annotations

from typing import Any, TypedDict

import pytest

from researchos.research_core.analysis_result import AnalysisResult, AnalysisState
from researchos.research_core.intelligence import ResearchContext, ResearchPlanner


class _AnalysisResultFromPlanKwargs(TypedDict):
    analysis_id: str
    claim_id: str
    population_definition: str
    time_window: str
    data_version: str
    feature_version: str
    label_version: str
    sample_size: int
    point_estimate: Any
    uncertainty_interval: tuple[float, float] | None
    probability_definition: str
    effect_size: Any
    result_artifact_hash: str


def _plan():
    plan, _ = ResearchPlanner().plan(
        ResearchContext(
            analysis_class="statistics",
            sample_size=100,
            dataset_id="dataset-1",
            dataset_sha256="a" * 64,
        )
    )
    return plan


def test_analysis_result_binds_plan_identity_and_is_deterministic() -> None:
    plan = _plan()
    kwargs: _AnalysisResultFromPlanKwargs = {
        analysis_id="analysis-1",
        claim_id="claim-1",
        population_definition="XAUUSD M1 returns",
        time_window="2021-01-01/2025-12-31",
        data_version="dataset-v1",
        feature_version="features-v1",
        label_version="labels-v1",
        sample_size=100,
        point_estimate={"mean": 0.01},
        uncertainty_interval=(-0.01, 0.03),
        probability_definition="not_applicable",
        effect_size=0.01,
        result_artifact_hash="b" * 64,
    )
    first = AnalysisResult.from_plan(plan, **kwargs)
    second = AnalysisResult.from_plan(plan, **kwargs)
    assert first.method == "quant.calculate_statistics.v1"
    assert first.data_hash == "a" * 64
    assert first.plan_sha256 == plan.plan_sha256
    assert first.result_sha256 == second.result_sha256


def test_analysis_result_rejects_validated_without_integrity_pass() -> None:
    plan = _plan()
    with pytest.raises(ValueError, match="integrity_gate_status=PASS"):
        AnalysisResult.from_plan(
            plan,
            analysis_id="a",
            claim_id="c",
            population_definition="p",
            time_window="t",
            data_version="d",
            feature_version="f",
            label_version="l",
            sample_size=100,
            point_estimate=1.0,
            uncertainty_interval=None,
            probability_definition="none",
            effect_size=1.0,
            result_artifact_hash="b" * 64,
            state=AnalysisState.VALIDATED,
            integrity_gate_status="FAIL",
        )


def test_analysis_result_rejects_multi_method_plan_at_single_result_boundary() -> None:
    plan = _plan()
    multi = type(plan)(
        plan_version=plan.plan_version,
        dataset_id=plan.dataset_id,
        dataset_sha256=plan.dataset_sha256,
        analysis_class=plan.analysis_class,
        selected_methods=(plan.selected_methods[0], "quant.calculate_returns.v1"),
        backend_by_method=plan.backend_by_method,
        selection_reasons=plan.selection_reasons,
        rejected_methods=plan.rejected_methods,
    )
    with pytest.raises(ValueError, match="exactly one selected method"):
        AnalysisResult.from_plan(
            multi,
            analysis_id="a",
            claim_id="c",
            population_definition="p",
            time_window="t",
            data_version="d",
            feature_version="f",
            label_version="l",
            sample_size=100,
            point_estimate=1.0,
            uncertainty_interval=None,
            probability_definition="none",
            effect_size=1.0,
            result_artifact_hash="b" * 64,
        )
