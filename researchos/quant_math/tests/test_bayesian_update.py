import pytest

from researchos.quant_math.bayesian_update import (
    BAYESIAN_UPDATE_VERSION,
    bayesian_update,
    condition_on_elimination,
    vos_savant_filter,
)
from researchos.quant_math.partition import ProbabilityPartition


def test_partition_enforces_invariants() -> None:
    partition = ProbabilityPartition.from_sequences(
        "market-state", ["A", "B", "C"], [1 / 3, 1 / 3, 1 / 3]
    )
    assert partition.to_dict()["partition_version"] == "PROBABILITY_PARTITION_V1"


@pytest.mark.parametrize(
    "probabilities",
    [[0.5, 0.6], [-0.1, 1.1], [float("inf"), 0.0]],
)
def test_partition_rejects_invalid_probability_vectors(probabilities) -> None:
    with pytest.raises(ValueError):
        ProbabilityPartition.from_sequences("invalid", ["A", "B"], probabilities)


def test_partition_rejects_duplicate_hypotheses() -> None:
    with pytest.raises(ValueError):
        ProbabilityPartition.from_sequences("invalid", ["A", "A"], [0.5, 0.5])


def test_bayesian_update_uses_likelihoods() -> None:
    partition = ProbabilityPartition.from_sequences(
        "three-state", ["A", "B", "C"], [1 / 3, 1 / 3, 1 / 3]
    )
    result = bayesian_update(
        partition,
        event_id="observe-not-C",
        likelihoods=[1.0, 1.0, 0.0],
        evidence_hash="event-hash",
    )
    assert result.posterior_probabilities == pytest.approx((0.5, 0.5, 0.0))
    assert result.evidence_probability == pytest.approx(2 / 3)
    assert result.update_version == BAYESIAN_UPDATE_VERSION
    assert result.verify()


def test_monty_hall_requires_host_policy_likelihoods() -> None:
    partition = ProbabilityPartition.from_sequences(
        "monty-hall", ["car-A", "car-B", "car-C"], [1 / 3, 1 / 3, 1 / 3]
    )
    # Player chose A; event is host opens C. Under a fair host policy:
    # P(event|A)=1/2, P(event|B)=1, P(event|C)=0.
    result = bayesian_update(
        partition,
        event_id="host-opened-C-after-choice-A",
        likelihoods=[0.5, 1.0, 0.0],
    )
    assert result.posterior_probabilities == pytest.approx((1 / 3, 2 / 3, 0.0))


def test_hard_elimination_is_exact_conditioning() -> None:
    partition = ProbabilityPartition.from_sequences(
        "three-state", ["A", "B", "C"], [1 / 3, 1 / 3, 1 / 3]
    )
    result = condition_on_elimination(
        partition, event_id="C-impossible", eliminated=[False, False, True]
    )
    assert result.posterior_probabilities == pytest.approx((0.5, 0.5, 0.0))


def test_vos_savant_filter_is_only_hard_elimination() -> None:
    assert vos_savant_filter(
        [0.2, 0.3, 0.5], [False, True, False]
    ) == pytest.approx((0.2857142857, 0.0, 0.7142857143))


def test_zero_predictive_probability_fails_closed() -> None:
    partition = ProbabilityPartition.from_sequences(
        "three-state", ["A", "B", "C"], [1 / 3, 1 / 3, 1 / 3]
    )
    with pytest.raises(ValueError, match="zero prior predictive"):
        bayesian_update(partition, event_id="impossible", likelihoods=[0.0, 0.0, 0.0])


def test_serialized_replay_and_tamper_detection() -> None:
    partition = ProbabilityPartition.from_sequences(
        "three-state", ["A", "B", "C"], [0.2, 0.3, 0.5]
    )
    result = bayesian_update(
        partition, event_id="e1", likelihoods=[0.9, 0.5, 0.1], evidence_hash="evidence-1"
    )
    replay = type(result).from_dict(result.to_dict())
    assert replay == result
    tampered = result.to_dict()
    tampered["posterior_probabilities"] = [1.0, 0.0, 0.0]
    with pytest.raises(ValueError, match="hash"):
        type(result).from_dict(tampered)


def test_unsupported_update_version_is_rejected_even_with_matching_hash() -> None:
    partition = ProbabilityPartition.from_sequences(
        "three-state", ["A", "B", "C"], [1 / 3, 1 / 3, 1 / 3]
    )
    result = bayesian_update(partition, event_id="e1", likelihoods=[1, 1, 0])
    payload = result.to_dict()
    payload["update_version"] = "BAYESIAN_UPDATE_V999"
    from researchos.core.identity import deterministic_hash
    unsigned = dict(payload)
    unsigned.pop("result_hash")
    payload["result_hash"] = deterministic_hash(unsigned)
    with pytest.raises(ValueError, match="hash"):
        type(result).from_dict(payload)
