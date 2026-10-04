"""Deterministic evaluation of prediction quality and calibration."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Iterable

from .experience import Experience


@dataclass(frozen=True)
class LearningMetrics:
    observations: int
    mean_predicted_probability: float
    empirical_outcome_rate: float
    brier_score: float
    mean_reward: float


class LearningEvaluator:
    """Compare predictions with observed outcomes without changing history."""

    @staticmethod
    def evaluate(experiences: Iterable[Experience]) -> LearningMetrics:
        rows = tuple(experiences)
        if not rows:
            return LearningMetrics(0, 0.0, 0.0, 0.0, 0.0)
        return LearningMetrics(
            observations=len(rows),
            mean_predicted_probability=mean(
                item.predicted_probability for item in rows
            ),
            empirical_outcome_rate=mean(item.outcome for item in rows),
            brier_score=mean(
                (item.predicted_probability - item.outcome) ** 2 for item in rows
            ),
            mean_reward=mean(item.reward for item in rows),
        )
