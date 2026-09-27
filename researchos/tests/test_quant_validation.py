"""
Unit tests for the Walk-Forward Validation Engine (WP-4 direct coverage).

Phase 5.1 — Certified Analytical Compute Surface (WP-4).
These tests observe the existing deterministic behavior of the validation
submodule. Pure research-only tests; no trading logic.

Covers:
    - WalkForwardSplitter chronological folds
    - WalkForwardValidator aggregate + per-fold results
    - Leakage detection / future-timestamp rejection
    - Determinism on identical inputs
    - Edge cases (too-small dataset, invalid config)
"""

import pytest

from researchos.quant_engine.machine_learning.dataset_contracts import ResearchDataset
from researchos.quant_engine.validation.contracts import ValidationError
from researchos.quant_engine.validation.splitter import WalkForwardSplitter
from researchos.quant_engine.validation.walk_forward import WalkForwardValidator


def _dataset(sample_count: int = 250, feature_count: int = 3) -> ResearchDataset:
    features = tuple(tuple(float(i + f) for f in range(feature_count)) for i in range(sample_count))
    labels = tuple(float(i % 2) for i in range(sample_count))
    return ResearchDataset(
        feature_names=tuple(f"f{f}" for f in range(feature_count)),
        features=features,
        labels=labels,
        sample_count=sample_count,
        feature_count=feature_count,
        label_name="target",
        metadata={"source": "test"},
    )


class TestSplitter:
    def test_split_chronological(self):
        splitter = WalkForwardSplitter(train_size=100, validation_size=50, step_size=50)
        folds = splitter.split(250)
        assert len(folds) >= 1
        for fold in folds:
            assert fold.train_start <= fold.train_end
            assert fold.validation_start <= fold.validation_end
            # Training must strictly precede validation.
            assert fold.train_end < fold.validation_start
            # Strictly chronological.
            assert fold.fold_id >= 1

    def test_split_no_overlap(self):
        splitter = WalkForwardSplitter(train_size=100, validation_size=50, step_size=50)
        folds = splitter.split(250)
        for i in range(1, len(folds)):
            assert folds[i].validation_start > folds[i - 1].validation_start

    def test_split_too_small(self):
        splitter = WalkForwardSplitter(train_size=100, validation_size=50, step_size=50)
        with pytest.raises(ValidationError):
            splitter.split(50)

    def test_split_invalid_train_size(self):
        with pytest.raises(ValidationError):
            WalkForwardSplitter(train_size=0, validation_size=50, step_size=50)


class TestValidator:
    # NOTE: the walk-forward validator requires a test tail to remain after the
    # final fold (no future leakage).  With train=100, val=50, step=50 the
    # folds tile at indices 149, 199, ..., 399.  A dataset of 401 samples
    # leaves index 400 as the untouched test tail.
    _VALIDATE_SIZE = 401

    def test_validate_returns_result(self):
        validator = WalkForwardValidator(train_size=100, validation_size=50, step_size=50)
        result = validator.validate(_dataset(self._VALIDATE_SIZE))
        assert result.fold_count >= 1
        assert result.train_size == 100
        assert result.validation_size == 50
        assert result.metrics is not None

    def test_validate_folds(self):
        validator = WalkForwardValidator(train_size=100, validation_size=50, step_size=50)
        fold_results = validator.validate_folds(_dataset(self._VALIDATE_SIZE))
        assert isinstance(fold_results, tuple)
        assert len(fold_results) >= 1
        for fr in fold_results:
            assert fr.sample_count > 0
            assert fr.metrics is not None

    def test_generate_report(self):
        validator = WalkForwardValidator(train_size=100, validation_size=50, step_size=50)
        report = validator.generate_report(_dataset(self._VALIDATE_SIZE))
        assert "fold_count" in report
        assert "metrics" in report
        assert "metadata" in report
        assert report["metadata"]["label_name"] == "target"
        assert report["metadata"]["feature_count"] == 3

    def test_validation_deterministic(self):
        validator = WalkForwardValidator(train_size=100, validation_size=50, step_size=50)
        ds = _dataset(self._VALIDATE_SIZE)
        r1 = validator.validate(ds)
        r2 = validator.validate(ds)
        assert r1.metrics == r2.metrics
        assert [fr.to_dict() for fr in r1.fold_results] == [fr.to_dict() for fr in r2.fold_results]

    def test_validate_requires_config(self):
        with pytest.raises(ValidationError):
            WalkForwardValidator(train_size=100)

    def test_validate_dataset_too_small(self):
        validator = WalkForwardValidator(train_size=100, validation_size=50, step_size=50)
        with pytest.raises(ValidationError):
            validator.validate(_dataset(50))

    def test_validate_wrong_type(self):
        validator = WalkForwardValidator(train_size=100, validation_size=50, step_size=50)
        with pytest.raises(TypeError):
            validator.validate({"not": "a dataset"})


class TestLeakageProtection:
    def test_leakage_requires_test_tail(self):
        # A dataset exactly matching train+validation should leave no test tail.
        validator = WalkForwardValidator(train_size=100, validation_size=50, step_size=50)
        with pytest.raises(ValidationError):
            validator.validate(_dataset(150))


    def test_explicit_holdout_size_is_reserved_and_reported(self):
        validator = WalkForwardValidator(
            train_size=100,
            validation_size=50,
            step_size=50,
            test_size=100,
        )
        result = validator.validate(_dataset(450))

        assert result.test_size == 100
        assert result.metadata["holdout_range"] == [350, 449]
        assert result.metadata["holdout_is_untouched"] is True
        assert result.fold_results[-1].validation_range == (300, 349)

    def test_explicit_holdout_boundary_must_follow_final_validation(self):
        validator = WalkForwardValidator(
            train_size=100,
            validation_size=50,
            step_size=50,
            test_size=100,
        )
        with pytest.raises(
            ValidationError,
            match="final validation window must end immediately before the explicit holdout",
        ):
            validator.validate(_dataset(425))

    def test_zero_explicit_holdout_is_rejected(self):
        with pytest.raises(ValidationError, match="test_size must be a positive integer"):
            WalkForwardValidator(
                train_size=100,
                validation_size=50,
                step_size=50,
                test_size=0,
            )

    def test_explicit_holdout_contributes_to_minimum_dataset_size(self):
        validator = WalkForwardValidator(
            train_size=100,
            validation_size=50,
            step_size=50,
            test_size=100,
        )
        with pytest.raises(ValidationError, match="train/validation/holdout"):
            validator.validate(_dataset(249))
