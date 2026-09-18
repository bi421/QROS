from researchos.research_core.intelligence import (
    DEFAULT_CAPABILITIES,
    Decision,
    ResearchContext,
    ResearchMethod,
    ResearchPlanner,
)


def test_planner_selects_only_eligible_method_and_records_rejections() -> None:
    planner = ResearchPlanner(DEFAULT_CAPABILITIES)
    plan, validation = planner.plan(
        ResearchContext(
            analysis_class="probability",
            sample_size=100,
            dataset_id="xauusd-m1",
            dataset_sha256="a" * 64,
        )
    )

    assert plan.selected_methods == ("probability.wilson.v1",)
    assert plan.plan_sha256
    assert validation.checks[:5] == (
        "dataset_integrity",
        "method_prerequisites",
        "no_lookahead_leakage",
        "result_provenance",
        "reproducibility",
    )
    rejected = {item.method_id: item.reasons for item in plan.rejected_methods}
    assert "analysis_class_not_supported" in rejected["risk.expected_shortfall.v1"]


def test_planner_rejects_insufficient_sample_without_running_method() -> None:
    planner = ResearchPlanner(DEFAULT_CAPABILITIES)
    try:
        planner.plan(
            ResearchContext(
                analysis_class="tail_risk",
                sample_size=13,
                dataset_id="small",
                dataset_sha256="b" * 64,
            )
        )
    except ValueError as exc:
        assert "insufficient_sample_size:13<30" in str(exc)
    else:
        raise AssertionError("planner must reject an ineligible computational path")


def test_time_series_path_requires_time_order_and_dependence() -> None:
    method = DEFAULT_CAPABILITIES.get("dependence.block_bootstrap.v1")
    decision, reasons = method.evaluate(
        ResearchContext(
            analysis_class="time_series",
            sample_size=100,
            has_time_order=True,
            has_serial_dependence=False,
        )
    )
    assert decision is Decision.NOT_ELIGIBLE
    assert reasons == ("serial_dependence_required",)


def test_plan_hash_is_stable_for_identical_context() -> None:
    planner = ResearchPlanner()
    context = ResearchContext(
        analysis_class="feature_information",
        sample_size=100,
        feature_names=frozenset({"feature", "target"}),
        dataset_id="d",
        dataset_sha256="c" * 64,
        multiple_testing_count=4,
        post_hoc=True,
    )
    first, validation = planner.plan(context)
    second, _ = planner.plan(context)
    assert first.plan_sha256 == second.plan_sha256
    assert "multiple_testing_control" in validation.checks
    assert "post_hoc_label" in validation.checks
