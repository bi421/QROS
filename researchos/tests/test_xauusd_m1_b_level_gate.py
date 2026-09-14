from __future__ import annotations

from scripts.evaluate_xauusd_m1_b_level_gate import (
    _bootstrap_ci,
    _permutation_pvalue,
    _two_sided_sign_test,
)


def test_sign_test_is_two_sided() -> None:
    assert _two_sided_sign_test(10, 0) == 0.001953125
    assert _two_sided_sign_test(5, 5) == 1.0


def test_exact_paired_permutation_is_deterministic() -> None:
    differences = [0.1] * 10
    first = _permutation_pvalue(differences, seed=20260914)
    second = _permutation_pvalue(differences, seed=20260914)
    assert first == second
    assert first[2] == "exact_sign_flip"
    assert first[0] < 0.01


def test_bootstrap_ci_is_deterministic_and_tracks_positive_effect() -> None:
    differences = [0.1, 0.2, 0.3, 0.4, 0.5]
    first = _bootstrap_ci(differences, seed=20260914)
    second = _bootstrap_ci(differences, seed=20260914)
    assert first == second
    assert first[0] > 0.0
    assert first[1] >= first[0]
