"""Tests for QROS Adaptive Learning Engine v1."""

import pytest

from researchos.learning import AdaptiveLearningEngine, Experience, ExperienceStore


def make_experience(
    index: int, outcome: float, probability: float = 0.6
) -> Experience:
    return Experience(
        experience_id=f"exp-{index}",
        state_key="TREND_UP|BREAKOUT",
        predicted_probability=probability,
        outcome=outcome,
        action="LONG",
        reward=1.0 if outcome else -1.0,
    )


def test_learning_updates_from_historical_outcomes() -> None:
    store = ExperienceStore(
        [make_experience(1, 1.0), make_experience(2, 0.0), make_experience(3, 1.0)]
    )
    engine = AdaptiveLearningEngine(store)

    update = engine.update_for_state("TREND_UP|BREAKOUT")

    assert update.observations == 3
    assert update.empirical_outcome_rate == pytest.approx(2 / 3)
    assert update.suggested_probability == pytest.approx(3 / 5)
    assert update.brier_score == pytest.approx((0.4**2 + 0.6**2 + 0.4**2) / 3)


def test_observe_is_append_only_and_updates_posterior() -> None:
    engine = AdaptiveLearningEngine()

    first = engine.observe(make_experience(1, 1.0))
    second = engine.observe(make_experience(2, 1.0))

    assert first.observations == 1
    assert second.observations == 2
    assert second.suggested_probability == pytest.approx(3 / 4)
    assert len(engine.store.all()) == 2


def test_duplicate_experience_is_rejected() -> None:
    engine = AdaptiveLearningEngine()
    engine.observe(make_experience(1, 1.0))

    with pytest.raises(ValueError, match="experience_id already exists"):
        engine.observe(make_experience(1, 0.0))


def test_invalid_probability_is_rejected() -> None:
    with pytest.raises(ValueError, match="predicted_probability"):
        Experience(
            experience_id="bad",
            state_key="state",
            predicted_probability=1.1,
            outcome=1.0,
            action="LONG",
            reward=1.0,
        )


def test_empty_state_has_neutral_prior() -> None:
    engine = AdaptiveLearningEngine()

    update = engine.update_for_state("UNSEEN")

    assert update.observations == 0
    assert update.suggested_probability == pytest.approx(0.5)
