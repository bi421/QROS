from researchos.research_core.intelligence import (
    DEFAULT_CAPABILITIES,
    ResearchContext,
    ResearchPlanner,
)


def test_planner_selects_real_quant_method_and_records_rejections() -> None:
    planner = ResearchPlanner(DEFAULT_CAPABILITIES)
    plan, validation = planner.plan(
        ResearchContext(
            analysis_class="statistics",
            sample_size=100,
            dataset_id="xauusd-m1",
            dataset_sha256="a" * 64,
        )
    )
    assert plan.selected_methods == ("quant.calculate_statistics.v1",)
    assert plan.plan_sha256
    assert validation.checks[:5] == (
        "dataset_integrity",
        "method_prerequisites",
        "no_lookahead_leakage",
        "result_provenance",
        "reproducibility",
    )
    rejected = {item.method_id: item.reasons for item in plan.rejected_methods}
    assert "analysis_class_not_supported" in rejected["quant.calculate_returns.v1"]


def test_planner_rejects_insufficient_sample_without_running_method() -> None:
    planner = ResearchPlanner(DEFAULT_CAPABILITIES)
    try:
        planner.plan(
            ResearchContext(
                analysis_class="drawdown",
                sample_size=1,
                dataset_id="small",
                dataset_sha256="b" * 64,
            )
        )
    except ValueError as exc:
        assert "insufficient_sample_size:1<2" in str(exc)
    else:
        raise AssertionError("planner must reject an ineligible computational path")


def test_planner_rejects_unsupported_analysis_class() -> None:
    planner = ResearchPlanner(DEFAULT_CAPABILITIES)
    try:
        planner.plan(
            ResearchContext(
                analysis_class="unsupported",
                sample_size=100,
                dataset_id="d",
                dataset_sha256="c" * 64,
            )
        )
    except ValueError as exc:
        assert "no eligible computational method" in str(exc)
    else:
        raise AssertionError("planner must reject an unsupported computational path")


def test_plan_hash_is_stable_for_identical_context() -> None:
    planner = ResearchPlanner()
    context = ResearchContext(
        analysis_class="statistics",
        sample_size=100,
        dataset_id="d",
        dataset_sha256="c" * 64,
        multiple_testing_count=4,
        post_hoc=True,
        out_of_sample=True,
    )
    first, validation = planner.plan(context)
    second, _ = planner.plan(context)
    assert first.plan_sha256 == second.plan_sha256
    assert "multiple_testing_control" in validation.checks
    assert "post_hoc_label" in validation.checks
    assert "out_of_sample_integrity" in validation.checks


def test_all_default_planner_methods_are_real_quant_operations() -> None:
    expected = {
        "quant.calculate_returns.v1",
        "quant.calculate_volatility.v1",
        "quant.calculate_drawdown.v1",
        "quant.calculate_statistics.v1",
        "quant.calculate_metrics.v1",
        "quant.calculate_performance_analytics.v1",
    }
    assert {method.method_id for method in DEFAULT_CAPABILITIES.methods()} == expected
