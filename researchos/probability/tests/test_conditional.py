"""Tests for canonical conditional/Bayes probability primitives."""
import pytest

from researchos.probability.conditional import (
    bayes_probability,
    bayes_probability_from_counts,
    conditional_probability,
    conditional_probability_from_counts,
)


def test_conditional_probability() -> None:
    assert conditional_probability(0.18, 0.30) == pytest.approx(0.60)


def test_bayes_probability() -> None:
    assert bayes_probability(0.80, 0.10, 0.20) == pytest.approx(0.40)


def test_count_based_conditional_probability() -> None:
    assert conditional_probability_from_counts(30, 50) == pytest.approx(0.60)


def test_count_based_bayes_probability() -> None:
    assert bayes_probability_from_counts(80, 100, 10, 100, 20, 100) == pytest.approx(0.40)


@pytest.mark.parametrize(
    "joint, condition",
    [(0.4, 0.3), (-0.1, 0.3), (0.1, 1.1), (0.0, 0.0)],
)
def test_invalid_conditional_inputs_rejected(joint: float, condition: float) -> None:
    with pytest.raises(ValueError):
        conditional_probability(joint, condition)
