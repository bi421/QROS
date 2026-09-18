import pytest

from researchos.research_core.multiple_testing import benjamini_hochberg, bonferroni


def test_bonferroni_preserves_original_order_and_controls_family_size():
    report = bonferroni([0.01, 0.20, 0.03])
    assert report.family_size == 3
    assert report.adjusted_p_values == pytest.approx((0.03, 0.60, 0.09))
    assert report.reject == (True, False, False)


def test_bh_adjustment_is_monotone_and_order_preserving():
    report = benjamini_hochberg([0.04, 0.01, 0.20, 0.03])
    assert report.adjusted_p_values == pytest.approx((0.05333333333333334, 0.04, 0.20, 0.05333333333333334))
    assert report.reject == (False, True, False, False)


def test_multiple_testing_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        bonferroni([])
    with pytest.raises(ValueError):
        benjamini_hochberg([1.1])
    with pytest.raises(ValueError):
        bonferroni([0.01], alpha=1.0)
