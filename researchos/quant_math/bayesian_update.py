from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from researchos.core.identity import deterministic_hash
from researchos.quant_math.partition import (
    PROBABILITY_TOLERANCE,
    ProbabilityPartition,
)

BAYESIAN_UPDATE_VERSION = "BAYESIAN_UPDATE_V1"


@dataclass(frozen=True)
class BayesianUpdateResult:
    """Auditable posterior produced from one explicit observation event."""

    partition_id: str
    event_id: str
    partition_version: str
    update_version: str
    hypotheses: tuple[str, ...]
    prior_probabilities: tuple[float, ...]
    likelihoods: tuple[float, ...]
    posterior_probabilities: tuple[float, ...]
    evidence_probability: float
    evidence_hash: str
    result_hash: str

    def to_dict(self, *, include_result_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "partition_id": self.partition_id,
            "event_id": self.event_id,
            "partition_version": self.partition_version,
            "update_version": self.update_version,
            "hypotheses": list(self.hypotheses),
            "prior_probabilities": list(self.prior_probabilities),
            "likelihoods": list(self.likelihoods),
            "posterior_probabilities": list(self.posterior_probabilities),
            "evidence_probability": self.evidence_probability,
            "evidence_hash": self.evidence_hash,
        }
        if include_result_hash:
            payload["result_hash"] = self.result_hash
        return payload

    def verify(self) -> bool:
        if self.update_version != BAYESIAN_UPDATE_VERSION:
            return False
        return deterministic_hash(self.to_dict(include_result_hash=False)) == self.result_hash

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "BayesianUpdateResult":
        required = (
            "partition_id", "event_id", "partition_version", "update_version",
            "hypotheses", "prior_probabilities", "likelihoods",
            "posterior_probabilities", "evidence_probability", "evidence_hash",
            "result_hash",
        )
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"missing Bayesian update fields: {missing}")
        obj = cls(
            partition_id=str(data["partition_id"]),
            event_id=str(data["event_id"]),
            partition_version=str(data["partition_version"]),
            update_version=str(data["update_version"]),
            hypotheses=tuple(str(value) for value in data["hypotheses"]),  # type: ignore[arg-type]
            prior_probabilities=tuple(float(value) for value in data["prior_probabilities"]),  # type: ignore[arg-type]
            likelihoods=tuple(float(value) for value in data["likelihoods"]),  # type: ignore[arg-type]
            posterior_probabilities=tuple(float(value) for value in data["posterior_probabilities"]),  # type: ignore[arg-type]
            evidence_probability=float(data["evidence_probability"]),
            evidence_hash=str(data["evidence_hash"]),
            result_hash=str(data["result_hash"]),
        )
        if not obj.verify():
            raise ValueError("Bayesian update result hash does not match content")
        return obj


def bayesian_update(
    partition: ProbabilityPartition,
    *,
    event_id: str,
    likelihoods: Sequence[float],
    evidence_hash: str = "",
) -> BayesianUpdateResult:
    """Apply Bayes: posterior is normalized prior times event likelihood."""
    if not event_id.strip():
        raise ValueError("event_id is required")
    if len(likelihoods) != len(partition.hypotheses):
        raise ValueError("likelihoods must match partition hypothesis count")
    normalized = tuple(float(value) for value in likelihoods)
    for likelihood in normalized:
        if not isfinite(likelihood) or not 0.0 <= likelihood <= 1.0:
            raise ValueError("likelihoods must be finite and within [0, 1]")

    weights = tuple(
        prior * likelihood
        for prior, likelihood in zip(partition.prior_probabilities, normalized)
    )
    evidence_probability = sum(weights)
    if not isfinite(evidence_probability) or evidence_probability <= 0.0:
        raise ValueError("observation has zero prior predictive probability")

    posterior = tuple(weight / evidence_probability for weight in weights)
    if abs(sum(posterior) - 1.0) > PROBABILITY_TOLERANCE:
        raise ValueError("posterior normalization failed")

    payload = {
        "partition_id": partition.partition_id,
        "event_id": event_id,
        "partition_version": partition.partition_version,
        "update_version": BAYESIAN_UPDATE_VERSION,
        "hypotheses": list(partition.hypotheses),
        "prior_probabilities": list(partition.prior_probabilities),
        "likelihoods": list(normalized),
        "posterior_probabilities": list(posterior),
        "evidence_probability": evidence_probability,
        "evidence_hash": evidence_hash,
    }
    return BayesianUpdateResult(
        partition_id=partition.partition_id,
        event_id=event_id,
        partition_version=partition.partition_version,
        update_version=BAYESIAN_UPDATE_VERSION,
        hypotheses=partition.hypotheses,
        prior_probabilities=partition.prior_probabilities,
        likelihoods=normalized,
        posterior_probabilities=posterior,
        evidence_probability=evidence_probability,
        evidence_hash=evidence_hash,
        result_hash=deterministic_hash(payload),
    )


def condition_on_elimination(
    partition: ProbabilityPartition,
    *,
    event_id: str,
    eliminated: Sequence[bool],
    evidence_hash: str = "",
) -> BayesianUpdateResult:
    """Hard-condition only when eliminated states are truly impossible."""
    if len(eliminated) != len(partition.hypotheses):
        raise ValueError("eliminated mask must match partition hypothesis count")
    likelihoods = tuple(0.0 if flag else 1.0 for flag in eliminated)
    return bayesian_update(
        partition, event_id=event_id, likelihoods=likelihoods, evidence_hash=evidence_hash
    )


def vos_savant_filter(
    prior_prob_vector: Sequence[float],
    eliminations_mask: Sequence[bool],
) -> tuple[float, ...]:
    """Compatibility helper for hard elimination, not a general Bayesian model."""
    if len(prior_prob_vector) != len(eliminations_mask):
        raise ValueError("probability vector and elimination mask must have equal length")
    partition = ProbabilityPartition.from_sequences(
        "vos-savant-filter",
        tuple(f"H{i}" for i in range(len(prior_prob_vector))),
        tuple(float(value) for value in prior_prob_vector),
    )
    return condition_on_elimination(
        partition, event_id="hard-elimination", eliminated=eliminations_mask
    ).posterior_probabilities
