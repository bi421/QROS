from researchos.research_core.edge_registry import (
    DEFAULT_EDGE_REGISTRY,
    EdgeDefinition,
    EdgeRegistry,
    EdgeState,
)
from researchos.research_core.evidence import EvidenceArtifact, EvidenceKind
from researchos.research_core.multiple_testing import adjust_p_values


DATASET_SHA = "a" * 64
CONTENT_SHA = "b" * 64


def _oos(sample_size: int = 100) -> EvidenceArtifact:
    return EvidenceArtifact(
        evidence_id="oos-1",
        kind=EvidenceKind.OUT_OF_SAMPLE,
        analysis_id="analysis-1",
        dataset_id="dataset-1",
        dataset_sha256=DATASET_SHA,
        partition_id="oos-2025",
        population_definition="future held-out observations",
        sample_size=sample_size,
        content_sha256=CONTENT_SHA,
    )


def _rep() -> EvidenceArtifact:
    return EvidenceArtifact(
        evidence_id="rep-1",
        kind=EvidenceKind.REPLICATION,
        analysis_id="analysis-1",
        dataset_id="dataset-2",
        dataset_sha256=DATASET_SHA,
        partition_id="replication-1",
        population_definition="independent replication observations",
        sample_size=100,
        content_sha256=CONTENT_SHA,
        independent_of_analysis_id="analysis-0",
    )


def _multiple_testing() -> object:
    return adjust_p_values((0.01, 0.20), method="holm")


def test_default_edge_requires_immutable_evidence_artifacts() -> None:
    snapshot = DEFAULT_EDGE_REGISTRY.evaluate(
        sample_size=29,
        out_of_sample=False,
        replicated=False,
        observed_effect_size=0.0,
    )
    decision = snapshot.decisions[0]
    assert decision.state is EdgeState.NOT_ELIGIBLE
    assert "insufficient_sample_size:29<30" in decision.reasons
    assert "multiple_testing_result_required" in decision.reasons
    assert "out_of_sample_evidence_artifact_required" in decision.reasons
    assert "replication_evidence_artifact_required" in decision.reasons


def test_default_edge_becomes_eligible_only_after_declared_gates() -> None:
    snapshot = DEFAULT_EDGE_REGISTRY.evaluate(
        sample_size=100,
        out_of_sample=True,
        replicated=True,
        observed_effect_size=0.1,
        uncertainty_lower_bound=0.05,
        out_of_sample_evidence_id="oos-1",
        replication_evidence_id="rep-1",
        out_of_sample_evidence=_oos(),
        replication_evidence=_rep(),
        multiple_testing_result=_multiple_testing(),
    )
    assert snapshot.decisions[0].state is EdgeState.ELIGIBLE
    assert snapshot.decisions[0].reasons == ()
    assert snapshot.registry_sha256


def test_registry_snapshot_is_deterministic() -> None:
    kwargs = dict(
        sample_size=100,
        out_of_sample=True,
        replicated=True,
        observed_effect_size=0.1,
        uncertainty_lower_bound=0.05,
        out_of_sample_evidence_id="oos-1",
        replication_evidence_id="rep-1",
        out_of_sample_evidence=_oos(),
        replication_evidence=_rep(),
        multiple_testing_result=_multiple_testing(),
    )
    assert DEFAULT_EDGE_REGISTRY.evaluate(**kwargs).registry_sha256 == (
        DEFAULT_EDGE_REGISTRY.evaluate(**kwargs).registry_sha256
    )


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
        "out_of_sample_evidence": _oos(),
        "replication_evidence": _rep(),
        "multiple_testing_result": _multiple_testing(),
    }


def test_multiple_testing_result_is_required() -> None:
    args = _passing_evidence()
    args["multiple_testing_result"] = None
    state, reasons = _strict_edge().evaluate(**args)
    assert state is EdgeState.NOT_ELIGIBLE
    assert reasons == ("multiple_testing_result_required",)


def test_multiple_testing_rejection_is_required() -> None:
    args = _passing_evidence()
    args["multiple_testing_result"] = adjust_p_values((0.9,), method="holm")
    state, reasons = _strict_edge().evaluate(**args)
    assert state is EdgeState.NOT_ELIGIBLE
    assert reasons == ("multiple_testing_not_rejected",)


def test_multiple_testing_hypothesis_index_is_validated() -> None:
    args = _passing_evidence()
    args["multiple_testing_hypothesis_index"] = 2
    state, reasons = _strict_edge().evaluate(**args)
    assert state is EdgeState.NOT_ELIGIBLE
    assert reasons == ("multiple_testing_hypothesis_index_invalid",)


def test_effect_below_minimum_blocks_eligibility() -> None:
    args = _passing_evidence()
    args["observed_effect_size"] = 0.09
    state, reasons = _strict_edge().evaluate(**args)
    assert state is EdgeState.NOT_ELIGIBLE
    assert reasons == ("effect_below_minimum:0.09<0.1",)


def test_uncertainty_lower_bound_below_minimum_blocks_eligibility() -> None:
    args = _passing_evidence()
    args["uncertainty_lower_bound"] = 0.09
    state, reasons = _strict_edge().evaluate(**args)
    assert state is EdgeState.NOT_ELIGIBLE
    assert reasons == ("uncertainty_below_minimum:0.09<0.1",)


def test_missing_oos_artifact_blocks_declared_oos() -> None:
    args = _passing_evidence()
    args["out_of_sample_evidence"] = None
    state, reasons = _strict_edge().evaluate(**args)
    assert state is EdgeState.NOT_ELIGIBLE
    assert "out_of_sample_evidence_artifact_required" in reasons


def test_missing_replication_artifact_blocks_declared_replication() -> None:
    args = _passing_evidence()
    args["replication_evidence"] = None
    state, reasons = _strict_edge().evaluate(**args)
    assert state is EdgeState.NOT_ELIGIBLE
    assert "replication_evidence_artifact_required" in reasons


def test_oos_artifact_kind_is_verified() -> None:
    args = _passing_evidence()
    args["out_of_sample_evidence"] = _rep()
    state, reasons = _strict_edge().evaluate(**args)
    assert state is EdgeState.NOT_ELIGIBLE
    assert "out_of_sample_evidence_kind_invalid" in reasons


def test_replication_artifact_requires_independence() -> None:
    try:
        EvidenceArtifact(
            evidence_id="rep-invalid",
            kind=EvidenceKind.REPLICATION,
            analysis_id="analysis-1",
            dataset_id="dataset-2",
            dataset_sha256=DATASET_SHA,
            partition_id="replication-1",
            population_definition="independent replication observations",
            sample_size=100,
            content_sha256=CONTENT_SHA,
            independent_of_analysis_id="analysis-1",
        )
    except ValueError as exc:
        assert "independent of the source analysis" in str(exc)
    else:
        raise AssertionError("self-replication must be rejected")


def test_evidence_hash_is_deterministic() -> None:
    assert _oos().evidence_sha256 == _oos().evidence_sha256
