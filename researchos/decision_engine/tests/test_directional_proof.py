from __future__ import annotations

from dataclasses import replace

import pytest

from researchos.decision_engine.directional_proof import (
    DirectionProofError,
    build_direction_proof,
)


def _evidence(directions_and_weights):
    return [
        {
            "source_id": f"evidence-{index}",
            "direction": direction,
            "weight": weight,
            "confidence": confidence,
        }
        for index, (direction, weight, confidence) in enumerate(directions_and_weights)
    ]


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([("Bullish", 1.0, 0.9), ("Bearish", 0.2, 0.5)], "UP"),
        ([("Bearish", 1.0, 0.9), ("Bullish", 0.2, 0.5)], "DOWN"),
        ([("Neutral", 1.0, 0.9), ("Bullish", 0.2, 0.1)], "NEUTRAL"),
        ([("Bullish", 0.0, 0.9), ("Bearish", 0.0, 0.8)], "NEUTRAL"),
        ([("Bullish", 1.0, 0.5), ("Bearish", 1.0, 0.5)], "NEUTRAL"),
    ],
)
def test_all_three_outputs_have_reproducible_mathematical_proof(items, expected):
    proof = build_direction_proof(
        model_id="WEIGHTED_EVIDENCE_V1",
        as_of="2026-10-12T09:00:00Z",
        horizon="M15",
        evidence=_evidence(items),
    )

    assert proof.direction == expected
    assert sum(proof.probabilities.values()) == pytest.approx(1.0, abs=1e-12)
    assert all(0.0 <= p <= 1.0 for p in proof.probabilities.values())
    proof.verify()
    assert proof.to_dict()["proof_sha256"] == proof.proof_sha256


def test_proof_is_deterministic_for_identical_inputs():
    kwargs = {
        "model_id": "WEIGHTED_EVIDENCE_V1",
        "as_of": "2026-10-12T09:00:00Z",
        "horizon": "M15",
        "evidence": _evidence([("Bullish", 0.8, 0.8), ("Neutral", 0.2, 0.5)]),
    }
    first = build_direction_proof(**kwargs)
    second = build_direction_proof(**kwargs)
    assert first.to_dict() == second.to_dict()


def test_verifier_rejects_tampered_probability():
    proof = build_direction_proof(
        model_id="WEIGHTED_EVIDENCE_V1",
        as_of="2026-10-12T09:00:00Z",
        horizon="M15",
        evidence=_evidence([("Bullish", 1.0, 0.9), ("Bearish", 1.0, 0.2)]),
    )
    altered = dict(proof.probabilities)
    altered["UP"] = 0.01
    with pytest.raises(DirectionProofError, match="probability failed independent recomputation"):
        replace(proof, probabilities=altered).verify()


def test_verifier_rejects_wrong_direction():
    proof = build_direction_proof(
        model_id="WEIGHTED_EVIDENCE_V1",
        as_of="2026-10-12T09:00:00Z",
        horizon="M15",
        evidence=_evidence([("Bullish", 1.0, 0.9), ("Bearish", 1.0, 0.2)]),
    )
    with pytest.raises(DirectionProofError, match="direction does not match"):
        replace(proof, direction="DOWN").verify()


@pytest.mark.parametrize(
    ("items", "message"),
    [
        ([("Bullish", 1.0, float("nan"))], "finite"),
        ([("sideways", 1.0, 0.5)], "unsupported evidence direction"),
        ([("Bullish", 2.0, 0.5)], "in \\[0, 1\\]"),
    ],
)
def test_invalid_evidence_fails_closed(items, message):
    with pytest.raises(DirectionProofError, match=message):
        build_direction_proof(
            model_id="WEIGHTED_EVIDENCE_V1",
            as_of="2026-10-12T09:00:00Z",
            horizon="M15",
            evidence=_evidence(items),
        )


def test_missing_timezone_fails_closed():
    with pytest.raises(DirectionProofError, match="timezone"):
        build_direction_proof(
            model_id="WEIGHTED_EVIDENCE_V1",
            as_of="2026-10-12T09:00:00",
            horizon="M15",
            evidence=[],
        )
