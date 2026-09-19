from __future__ import annotations

import pytest

from researchos.research_core.multiple_testing import (
    MULTIPLE_TESTING_SCHEMA_VERSION,
    adjust_p_values,
)


def test_holm_preserves_input_order_and_is_deterministic() -> None:
    result = adjust_p_values([0.01, 0.04, 0.20], method="holm")
    assert result.schema_version == MULTIPLE_TESTING_SCHEMA_VERSION
    assert result.adjusted_p_values == pytest.approx((0.03, 0.08, 0.20))
    assert result.reject() == (True, False, False)
    assert result.to_dict() == result.to_dict()


def test_benjamini_hochberg_adjustment_is_monotone_in_sorted_order() -> None:
    result = adjust_p_values([0.01, 0.04, 0.20, 0.60], method="benjamini_hochberg")
    assert result.adjusted_p_values == pytest.approx((0.04, 0.08, 0.2666666667, 0.6))
    assert result.reject() == (True, False, False, False)


def test_invalid_method_and_probability_are_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported multiple-testing method"):
        adjust_p_values([0.05], method="bonferroni")
    with pytest.raises(ValueError, match="p_values"):
        adjust_p_values([1.1], method="holm")


def test_empty_input_is_valid_and_deterministic() -> None:
    result = adjust_p_values([], method="holm")
    assert result.adjusted_p_values == ()
    assert result.reject() == ()
