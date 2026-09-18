from researchos.research_core.edge_registry import (
    DEFAULT_EDGE_REGISTRY,
    EdgeDefinition,
    EdgeRegistry,
    EdgeState,
)


def test_default_edge_requires_oos_replication_and_sample() -> None:
    snapshot = DEFAULT_EDGE_REGISTRY.evaluate(
        sample_size=29,
        out_of_sample=False,
        replicated=False,
        observed_effect_size=0.0,
    )
    decision = snapshot.decisions[0]
    assert decision.state is EdgeState.NOT_ELIGIBLE
    assert decision.reasons == (
        "insufficient_sample_size:29<30",
        "uncertainty_required",
        "out_of_sample_required",
        "out_of_sample_evidence_required",
        "replication_required",
        "replication_evidence_required",
    )


def test_default_edge_becomes_eligible_only_after_declared_gates() -> None:
    snapshot = DEFAULT_EDGE_REGISTRY.evaluate(
        sample_size=30,
        out_of_sample=True,
        replicated=True,
        observed_effect_size=0.1,
        uncertainty_lower_bound=0.05,
        out_of_sample_evidence_id="oos-1",
        replication_evidence_id="rep-1",
    )
    assert snapshot.decisions[0].state is EdgeState.ELIGIBLE
    assert snapshot.decisions[0].reasons == ()
    assert snapshot.registry_sha256


def test_registry_snapshot_is_deterministic() -> None:
    first = DEFAULT_EDGE_REGISTRY.evaluate(
        sample_size=100,
        out_of_sample=True,
        replicated=True,
        observed_effect_size=0.1,
        uncertainty_lower_bound=0.05,
        out_of_sample_evidence_id="oos-1",
        replication_evidence_id="rep-1",
    )
    second = DEFAULT_EDGE_REGISTRY.evaluate(
        sample_size=100,
        out_of_sample=True,
        replicated=True,
        observed_effect_size=0.1,
        uncertainty_lower_bound=0.05,
        out_of_sample_evidence_id="oos-1",
        replication_evidence_id="rep-1",
    )
    assert first.registry_sha256 == second.registry_sha256


def test_duplicate_edge_ids_are_rejected() -> None:
    definition = DEFAULT_EDGE_REGISTRY.definitions()[0]
    try:
        EdgeRegistry((definition, definition))
    except ValueError as exc:
        assert "duplicate edge_id" in str(exc)
    else:
        raise AssertionError("duplicate edge ids must be rejected")


def _strict_edge() -> EdgeDefinition:
    return EdgeDefinition(
        edge_id="test.strict_edge.v1",
        version="1",
        outcome_definition="binary event",
        null_definition="baseline rate",
        minimum_effect_size=0.10,
        minimum_sample_size=30,
    )


def _passing_evidence() -> dict[str, object]:
    return {
        "sample_size": 100,
        "out_of_sample": True,
        "replicated": True,
        "observed_effect_size": 0.15,
        "uncertainty_lower_bound": 0.12,
        "out_of_sample_evidence_id": "oos-1",
        "replication_evidence_id": "rep-1",
    }


def test_effect_below_minimum_blocks_eligibility() -> None:
    edge = _strict_edge()
    args = _passing_evidence()
    args["observed_effect_size"] = 0.09
    state, reasons = edge.evaluate(**args)
    assert state is EdgeState.NOT_ELIGIBLE
    assert reasons == ("effect_below_minimum:0.09<0.1",)


def test_uncertainty_lower_bound_below_minimum_blocks_eligibility() -> None:
    edge = _strict_edge()
    args = _passing_evidence()
    args["uncertainty_lower_bound"] = 0.09
    state, reasons = edge.evaluate(**args)
    assert state is EdgeState.NOT_ELIGIBLE
    assert reasons == ("uncertainty_below_minimum:0.09<0.1",)


def test_missing_oos_evidence_blocks_declared_oos() -> None:
    edge = _strict_edge()
    args = _passing_evidence()
    args["out_of_sample_evidence_id"] = None
    state, reasons = edge.evaluate(**args)
    assert state is EdgeState.NOT_ELIGIBLE
    assert reasons == ("out_of_sample_evidence_required",)


def test_missing_replication_evidence_blocks_declared_replication() -> None:
    edge = _strict_edge()
    args = _passing_evidence()
    args["replication_evidence_id"] = None
    state, reasons = edge.evaluate(**args)
    assert state is EdgeState.NOT_ELIGIBLE
    assert reasons == ("replication_evidence_required",)
