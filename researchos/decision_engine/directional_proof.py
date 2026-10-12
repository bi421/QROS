"""Proof-carrying three-way direction output for weighted research evidence.

The proof independently recomputes the existing Decision Engine formula:
contribution_i = confidence_i * weight_i
P(class) = class_contribution / total_contribution
If all contributions are zero, the defined fallback is a uniform distribution.
This proves calculation integrity, not future market outcomes or calibration.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from typing import Any, Mapping

DIRECTIONS = ("UP", "DOWN", "NEUTRAL")
CONTRACT_VERSION = "THREE_WAY_DIRECTION_PROOF_V1"
_SEMANTICS = "weighted_evidence_probability_not_empirically_calibrated_by_this_proof"


class DirectionProofError(ValueError):
    """Raised when direction evidence or its proof contract is invalid."""


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    )


def _parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise DirectionProofError("as_of must be a non-empty ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DirectionProofError("as_of must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DirectionProofError("as_of must include a timezone offset")
    return parsed


def _normalize_direction(value: Any) -> str:
    normalized = str(value).strip().upper()
    mapping = {"BULLISH": "UP", "BEARISH": "DOWN", "NEUTRAL": "NEUTRAL"}
    if normalized not in mapping:
        raise DirectionProofError(f"unsupported evidence direction: {value!r}")
    return mapping[normalized]


def _calculate(evidence: list[dict[str, Any]]) -> tuple[dict[str, float], dict[str, float]]:
    contributions = {direction: 0.0 for direction in DIRECTIONS}
    for index, item in enumerate(evidence):
        direction = _normalize_direction(item.get("direction"))
        weight = item.get("weight")
        confidence = item.get("confidence")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise DirectionProofError(f"evidence[{index}].weight must be numeric")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise DirectionProofError(f"evidence[{index}].confidence must be numeric")
        weight, confidence = float(weight), float(confidence)
        if not math.isfinite(weight) or not 0.0 <= weight <= 1.0:
            raise DirectionProofError(f"evidence[{index}].weight must be finite and in [0, 1]")
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise DirectionProofError(f"evidence[{index}].confidence must be finite and in [0, 1]")
        contributions[direction] += confidence * weight

    total = math.fsum(contributions.values())
    if total == 0.0:
        probabilities = {direction: 1.0 / 3.0 for direction in DIRECTIONS}
    else:
        probabilities = {direction: contributions[direction] / total for direction in DIRECTIONS}
        # Match the canonical calculator's residual assignment to neutral.
        probabilities["NEUTRAL"] = max(0.0, 1.0 - probabilities["UP"] - probabilities["DOWN"])
    return contributions, probabilities


def _select_direction(probabilities: Mapping[str, float]) -> str:
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
    as_of: str
    horizon: str
    evidence: list[dict[str, Any]]
    source_data_sha256: str
    contributions: dict[str, float]
    probabilities: dict[str, float]
    direction: str
    probability_semantics: str
    proof_sha256: str

    def payload(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "model_id": self.model_id,
            "as_of": self.as_of,
            "horizon": self.horizon,
            "evidence": self.evidence,
            "source_data_sha256": self.source_data_sha256,
            "contributions": self.contributions,
            "probabilities": self.probabilities,
            "direction": self.direction,
            "probability_semantics": self.probability_semantics,
        }

    def verify(self) -> None:
        """Recompute the weighted formula from embedded evidence and verify hashes."""
        if self.contract_version != CONTRACT_VERSION:
            raise DirectionProofError("unsupported proof contract version")
        if not self.model_id.strip() or not self.horizon.strip():
            raise DirectionProofError("model_id and horizon are required")
        _parse_timestamp(self.as_of)
        if not isinstance(self.evidence, list):
            raise DirectionProofError("evidence must be a list")
        expected_source_hash = hashlib.sha256(
            _canonical_json(self.evidence).encode("utf-8")
        ).hexdigest()
        if self.source_data_sha256 != expected_source_hash:
            raise DirectionProofError("source_data_sha256 does not match embedded evidence")

        # Separate recomputation in the verifier; do not trust stored outputs.
        expected_contributions = {direction: 0.0 for direction in DIRECTIONS}
        for index, item in enumerate(self.evidence):
            direction_value = str(item.get("direction", "")).strip().upper()
            direction = {"BULLISH": "UP", "BEARISH": "DOWN", "NEUTRAL": "NEUTRAL"}.get(direction_value, direction_value)
            if direction not in expected_contributions:
                raise DirectionProofError(f"unsupported evidence direction at index {index}")
            weight, confidence = item.get("weight"), item.get("confidence")
            if isinstance(weight, bool) or isinstance(confidence, bool):
                raise DirectionProofError(f"invalid numeric input at evidence index {index}")
            if not isinstance(weight, (int, float)) or not isinstance(confidence, (int, float)):
                raise DirectionProofError(f"invalid numeric input at evidence index {index}")
            if not math.isfinite(weight) or not math.isfinite(confidence):
                raise DirectionProofError(f"non-finite numeric input at evidence index {index}")
            if not 0 <= weight <= 1 or not 0 <= confidence <= 1:
                raise DirectionProofError(f"out-of-range numeric input at evidence index {index}")
            expected_contributions[direction] += float(weight) * float(confidence)

        total = sum(expected_contributions.values())
        if total == 0:
            expected_probabilities = {direction: 1.0 / 3.0 for direction in DIRECTIONS}
        else:
            expected_probabilities = {
                direction: expected_contributions[direction] / total
                for direction in DIRECTIONS
            }
            expected_probabilities["NEUTRAL"] = max(
                0.0, 1.0 - expected_probabilities["UP"] - expected_probabilities["DOWN"]
            )
        if set(self.contributions) != set(DIRECTIONS) or set(self.probabilities) != set(DIRECTIONS):
            raise DirectionProofError("contributions and probabilities must contain all three directions")
        for direction in DIRECTIONS:
            if not math.isclose(self.contributions[direction], expected_contributions[direction], rel_tol=1e-12, abs_tol=1e-15):
                raise DirectionProofError(f"{direction} contribution failed independent recomputation")
            actual = self.probabilities[direction]
            if not math.isfinite(actual) or not 0 <= actual <= 1:
                raise DirectionProofError(f"{direction} probability must be finite and in [0, 1]")
            if not math.isclose(actual, expected_probabilities[direction], rel_tol=1e-12, abs_tol=1e-15):
                raise DirectionProofError(f"{direction} probability failed independent recomputation")
        if not math.isclose(sum(self.probabilities.values()), 1.0, rel_tol=0, abs_tol=1e-12):
            raise DirectionProofError("probabilities must sum to one")
        if self.direction not in DIRECTIONS or self.direction != _select_direction(expected_probabilities):
            raise DirectionProofError("direction does not match the declared maximum-probability rule")
        if self.probability_semantics != _SEMANTICS:
            raise DirectionProofError("unverified probability semantics")
        expected_proof_hash = hashlib.sha256(
            _canonical_json(self.payload()).encode("utf-8")
        ).hexdigest()
        if self.proof_sha256 != expected_proof_hash:
            raise DirectionProofError("proof_sha256 does not match proof payload")

    def to_dict(self) -> dict[str, object]:
        result = self.payload()
        result["proof_sha256"] = self.proof_sha256
        return result


def build_direction_proof(
    *,
    model_id: str,
    as_of: str,
    horizon: str,
    evidence: list[Mapping[str, Any]],
) -> ThreeWayDirectionProof:
    """Build and self-verify a proof from the canonical weighted-evidence formula."""
    if not isinstance(model_id, str) or not model_id.strip():
        raise DirectionProofError("model_id is required")
    if not isinstance(horizon, str) or not horizon.strip():
        raise DirectionProofError("horizon is required")
    _parse_timestamp(as_of)
    canonical_evidence = [dict(item) for item in evidence]
    source_hash = hashlib.sha256(_canonical_json(canonical_evidence).encode("utf-8")).hexdigest()
    contributions, probabilities = _calculate(canonical_evidence)
    direction = _select_direction(probabilities)
    unsigned = {
        "contract_version": CONTRACT_VERSION,
        "model_id": model_id,
        "as_of": as_of,
        "horizon": horizon,
        "evidence": canonical_evidence,
        "source_data_sha256": source_hash,
        "contributions": contributions,
        "probabilities": probabilities,
        "direction": direction,
        "probability_semantics": _SEMANTICS,
    }
    proof = ThreeWayDirectionProof(
        contract_version=CONTRACT_VERSION,
        model_id=model_id,
        as_of=as_of,
        horizon=horizon,
        evidence=canonical_evidence,
        source_data_sha256=source_hash,
        contributions=contributions,
        probabilities=probabilities,
        direction=direction,
        probability_semantics=_SEMANTICS,
        proof_sha256=hashlib.sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest(),
    )
    proof.verify()
    return proof
