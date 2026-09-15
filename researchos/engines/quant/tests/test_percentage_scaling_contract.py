"""Regression tests for the fractional percentage-return contract."""

import pytest

from researchos.quant_engine.backend import PythonQuantBackend


@pytest.mark.parametrize(
    ("prices", "expected"),
    [
        ([100.0, 102.0, 101.0, 105.0], [0.02, -1.0 / 102.0, 4.0 / 101.0]),
    ],
)
def test_percentage_returns_are_fractions(prices, expected):
    """Percentage returns are fractions (0.02 = 2%), never 2.0 = 200%."""
    actual = PythonQuantBackend().calculate_returns(prices, "percentage")
    assert actual == pytest.approx(expected, abs=1e-12)
