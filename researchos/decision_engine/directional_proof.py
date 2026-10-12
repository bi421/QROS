"""Proof-carrying three-way direction classification.

This module verifies the mathematics and provenance of a UP/DOWN/NEUTRAL
classification. Softmax outputs are normalized model-score probabilities; they
are not claimed to be empirically calibrated unless a separate calibration
artifact is supplied by a governed upstream stage.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
import re
from typing import Mapping

DIRECTIONS = ("UP", "DOWN", "NEUTRAL")
CONTRACT_VERSION = "THREE_WAY_DIRECTION_PROOF_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DirectionProofError(ValueError):
    """Raised when direction evidence or its proof contract is invalid."""


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    )


def _validate_timestamp(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DirectionProofError(f"{field} must be a non-empty ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DirectionProofError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DirectionProofError(f"{field} must include a timezone offset")


def _validate_scores(scores: Mapping[str, float]) -> dict[str, float]:
    if set(scores) != set(DIRECTIONS):
        raise DirectionProofError("scores must contain exactly UP, DOWN, and NEUTRAL")
    normalized: dict[str, float] = {}
    for direction in DIRECTIONS:
        value = scores[direction]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DirectionProofError(f"{direction} score must be numeric")
        score = float(value)
        if not math.isfinite(score):
            raise DirectionProofError(f"{direction} score must be finite")
        normalized[direction] = score
    return normalized


def _softmax(scores: Mapping[str, float], temperature: float) -> dict[str, float]:
    """Stable softmax: p_i = exp(s_i/T - m) / sum_j exp(s_j/T - m)."""
    maximum = max(scores.values()) / temperature
    exponentials = {
        direction: math.exp(score / temperature - maximum)
        for direction, score in scores.items()
    }
    denominator = math.fsum(exponentials.values())
    return {
        direction: exponentials[direction] / denominator
        for direction in DIRECTIONS
    }


def _select_direction(probabilities: Mapping[str, float]) -> str:
    """A tie at the maximum resolves to NEUTRAL, otherwise choose the max."""
    maximum = max(probabilities.values())
    winners = [
        direction for direction in DIRECTIONS
        if math.isclose(probabilities[direction], maximum, rel_tol=1e-12, abs_tol=1e-15)
    ]
    return winners[0] if len(winners) == 1 else "NEUTRAL"


@dataclass(frozen=True)
class ThreeWayDirectionProof:
    contract_version: str
    model_id: str
    source_data_sha256: str
    as_of: str
    horizon: str
    temperature: float
    scores: dict[str, float]
    probabilities: dict[str, float]
    direction: str
    probability_semantics: str
    proof_sha256: str

    def payload(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "model_id": self.model_id,
            "source_data_sha256": self.source_data_sha256,
            "as_of": self.as_of,
            "horizon": self.horizon,
            "temperature": self.temperature,
            "scores": self.scores,
            "probabilities": self.probabilities,
            "direction": self.direction,
            "probability_semantics": self.probability_semantics,
        }

    def verify(self) -> None:
        """Independently re-check provenance, softmax, class decision, and hash."""
        if self.contract_version != CONTRACT_VERSION:
            raise DirectionProofError("unsupported proof contract version")
        if not self.model_id.strip() or not self.horizon.strip():
            raise DirectionProofError("model_id and horizon are required")
        if not _SHA256_RE.fullmatch(self.source_data_sha256):
            raise DirectionProofError("source_data_sha256 must be a lowercase SHA-256 digest")
        _validate_timestamp(self.as_of, "as_of")
        if not math.isfinite(self.temperature) or self.temperature <= 0:
            raise DirectionProofError("temperature must be finite and greater than zero")
        scores = _validate_scores(self.scores)

        # Deliberately recompute using a separate verifier expression rather
        # than trusting the probabilities embedded in the submitted artifact.
        scaled = {key: scores[key] / self.temperature for key in DIRECTIONS}
        shift = max(scaled.values())
        terms = {key: math.exp(scaled[key] - shift) for key in DIRECTIONS}
        total = sum(terms[key] for key in DIRECTIONS)
        expected = {key: terms[key] / total for key in DIRECTIONS}

        if set(self.probabilities) != set(DIRECTIONS):
            raise DirectionProofError("probabilities must contain exactly UP, DOWN, and NEUTRAL")
        for key in DIRECTIONS:
            actual = self.probabilities[key]
            if not math.isfinite(actual) or not 0.0 <= actual <= 1.0:
                raise DirectionProofError(f"{key} probability must be finite and in [0, 1]")
            if not math.isclose(actual, expected[key], rel_tol=1e-12, abs_tol=1e-15):
                raise DirectionProofError(f"{key} probability does not match softmax recomputation")
        if not math.isclose(math.fsum(self.probabilities.values()), 1.0, rel_tol=0, abs_tol=1e-12):
            raise DirectionProofError("probabilities must sum to one")
        if self.direction not in DIRECTIONS:
            raise DirectionProofError("direction must be UP, DOWN, or NEUTRAL")
        if self.direction != _select_direction(expected):
            raise DirectionProofError("direction does not match the declared decision rule")
        if self.probability_semantics != "normalized_model_score_not_calibrated_probability":
            raise DirectionProofError("unverified probability semantics")
        expected_hash = hashlib.sha256(_canonical_json(self.payload()).encode("utf-8")).hexdigest()
        if self.proof_sha256 != expected_hash:
            raise DirectionProofError("proof_sha256 does not match the proof payload")

    def to_dict(self) -> dict[str, object]:
        result = self.payload()
        result["proof_sha256"] = self.proof_sha256
        return result


def build_direction_proof(
    *,
    model_id: str,
    source_data_sha256: str,
    as_of: str,
    horizon: str,
    scores: Mapping[str, float],
    temperature: float = 1.0,
) -> ThreeWayDirectionProof:
    """Create and self-verify a deterministic three-class direction proof."""
    if not isinstance(model_id, str) or not model_id.strip():
        raise DirectionProofError("model_id is required")
    if not isinstance(horizon, str) or not horizon.strip():
        raise DirectionProofError("horizon is required")
    if not isinstance(source_data_sha256, str) or not _SHA256_RE.fullmatch(source_data_sha256):
        raise DirectionProofError("source_data_sha256 must be a lowercase SHA-256 digest")
    _validate_timestamp(as_of, "as_of")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise DirectionProofError("temperature must be numeric")
    temperature = float(temperature)
    if not math.isfinite(temperature) or temperature <= 0:
        raise DirectionProofError("temperature must be finite and greater than zero")

    normalized_scores = _validate_scores(scores)
    probabilities = _softmax(normalized_scores, temperature)
    direction = _select_direction(probabilities)
    unsigned = {
        "contract_version": CONTRACT_VERSION,
        "model_id": model_id,
        "source_data_sha256": source_data_sha256,
        "as_of": as_of,
        "horizon": horizon,
        "temperature": temperature,
        "scores": normalized_scores,
        "probabilities": probabilities,
        "direction": direction,
        "probability_semantics": "normalized_model_score_not_calibrated_probability",
    }
    proof = ThreeWayDirectionProof(
        **unsigned,
        proof_sha256=hashlib.sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest(),
    )
    proof.verify()
    return proof
