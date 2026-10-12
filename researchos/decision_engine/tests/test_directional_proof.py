from __future__ import annotations

from dataclasses import replace

import pytest

from researchos.decision_engine.directional_proof import (
    DirectionProofError,
    build_direction_proof,
)


SOURCE_HASH = "a" * 64
AS_OF = "2026-10-12T09:00:00Z"


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        ({"UP": 3.0, "DOWN": 1.0, "NEUTRAL": 0.0}, "UP"),
        ({"UP": -1.0, "DOWN": 4.0, "NEUTRAL": 0.0}, "DOWN"),
        ({"UP": 0.0, "DOWN": 0.0, "NEUTRAL": 2.0}, "NEUTRAL"),
        ({"UP": 1.0, "DOWN": 1.0, "NEUTRAL": 0.0}, "NEUTRAL"),
        ({"UP": 0.0, "DOWN": 0.0, "NEUTRAL": 0.0}, "NEUTRAL"),
    ],
)
def test_all_three_outputs_have_reproducible_mathematical_proof(scores, expected):
    proof = build_direction_proof(
        model_id="test-model-v1",
        source_data_sha256=SOURCE_HASH,
        as_of=AS_OF,
        horizon="M15",
        scores=scores,
    )

    assert proof.direction == expected
    assert sum(proof.probabilities.values()) == pytest.approx(1.0, abs=1e-12)
    assert all(0.0 <= p <= 1.0 for p in proof.probabilities.values())
    proof.verify()
    assert proof.to_dict()["proof_sha256"] == proof.proof_sha256


def test_proof_is_deterministic_for_identical_inputs():
    kwargs = {
        "model_id": "test-model-v1",
        "source_data_sha256": SOURCE_HASH,
        "as_of": AS_OF,
        "horizon": "M15",
        "scores": {"UP": 0.8, "DOWN": 0.2, "NEUTRAL": -0.1},
    }
    first = build_direction_proof(**kwargs)
    second = build_direction_proof(**kwargs)
    assert first.to_dict() == second.to_dict()


def test_verifier_rejects_tampered_probability_even_if_hash_is_stale():
    proof = build_direction_proof(
        model_id="test-model-v1",
        source_data_sha256=SOURCE_HASH,
        as_of=AS_OF,
        horizon="M15",
        scores={"UP": 2.0, "DOWN": 1.0, "NEUTRAL": 0.0},
    )
    altered = dict(proof.probabilities)
    altered["UP"] = 0.01
    with pytest.raises(DirectionProofError, match="softmax recomputation"):
        replace(proof, probabilities=altered).verify()


def test_verifier_rejects_wrong_direction():
    proof = build_direction_proof(
        model_id="test-model-v1",
        source_data_sha256=SOURCE_HASH,
        as_of=AS_OF,
        horizon="M15",
        scores={"UP": 2.0, "DOWN": 1.0, "NEUTRAL": 0.0},
    )
    with pytest.raises(DirectionProofError, match="direction does not match"):
        replace(proof, direction="DOWN").verify()


@pytest.mark.parametrize(
    ("scores", "message"),
    [
        ({"UP": 1.0, "DOWN": float("nan"), "NEUTRAL": 0.0}, "finite"),
        ({"UP": 1.0, "DOWN": 0.0}, "exactly UP, DOWN, and NEUTRAL"),
        ({"UP": True, "DOWN": 0.0, "NEUTRAL": 0.0}, "numeric"),
    ],
)
def test_invalid_scores_fail_closed(scores, message):
    with pytest.raises(DirectionProofError, match=message):
        build_direction_proof(
            model_id="test-model-v1",
            source_data_sha256=SOURCE_HASH,
            as_of=AS_OF,
            horizon="M15",
            scores=scores,
        )


def test_missing_source_hash_or_timezone_fails_closed():
    with pytest.raises(DirectionProofError, match="SHA-256"):
        build_direction_proof(
            model_id="test-model-v1",
            source_data_sha256="missing",
            as_of=AS_OF,
            horizon="M15",
            scores={"UP": 1.0, "DOWN": 0.0, "NEUTRAL": 0.0},
        )
    with pytest.raises(DirectionProofError, match="timezone"):
        build_direction_proof(
            model_id="test-model-v1",
            source_data_sha256=SOURCE_HASH,
            as_of="2026-10-12T09:00:00",
            horizon="M15",
            scores={"UP": 1.0, "DOWN": 0.0, "NEUTRAL": 0.0},
        )
