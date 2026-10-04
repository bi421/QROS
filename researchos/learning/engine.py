"""QROS Adaptive Learning Engine v1 closed-loop coordinator."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .evaluator import LearningEvaluator, LearningMetrics
from .experience import Experience, ExperienceStore


@dataclass(frozen=True)
class LearningUpdate:
    """Evidence returned after recording an outcome."""

    state_key: str
    observations: int
    empirical_outcome_rate: float
    brier_score: float
    suggested_probability: float


class AdaptiveLearningEngine:
    """Learn from historical and newly observed outcomes, never from mutation.

    v1 uses a Beta(1, 1) prior per state.  The suggested probability is the
    posterior mean, which is deliberately an evidence update rather than an
    automatic strategy or risk-policy mutation.
    """

    VERSION = "adaptive-learning-v1"

    def __init__(self, store: ExperienceStore | None = None) -> None:
        self.store = store or ExperienceStore()
        self.evaluator = LearningEvaluator()

    def observe(self, experience: Experience) -> LearningUpdate:
        self.store.append(experience)
        return self.update_for_state(experience.state_key)

    def update_for_state(self, state_key: str) -> LearningUpdate:
        rows = self.store.for_state(state_key)
        metrics = self.evaluator.evaluate(rows)
        successes = sum(item.outcome for item in rows)
        failures = sum(1.0 - item.outcome for item in rows)
        suggested = (1.0 + successes) / (2.0 + successes + failures)
        return LearningUpdate(
            state_key=state_key,
            observations=metrics.observations,
            empirical_outcome_rate=metrics.empirical_outcome_rate,
            brier_score=metrics.brier_score,
            suggested_probability=suggested,
        )

    def evaluate(self, state_key: str | None = None) -> LearningMetrics:
        rows = self.store.all() if state_key is None else self.store.for_state(state_key)
        return self.evaluator.evaluate(rows)

    @staticmethod
    def validate_probability(value: float) -> float:
        if not isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("probability must be finite and in [0, 1]")
        return value
