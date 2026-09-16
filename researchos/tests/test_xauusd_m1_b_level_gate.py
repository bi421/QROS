from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

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


def test_gate_script_supports_direct_help_execution() -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_xauusd_m1_b_level_gate.py"

    with tempfile.TemporaryDirectory() as temp_dir:
        stdout_path = Path(temp_dir) / "stdout.txt"
        stderr_path = Path(temp_dir) / "stderr.txt"

        with (
            stdout_path.open("w", encoding="utf-8") as stdout_file,
            stderr_path.open("w", encoding="utf-8") as stderr_file,
        ):
            completed = subprocess.run(
                [sys.executable, str(script), "--help"],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
            )

        stdout = stdout_path.read_text(encoding="utf-8")
        stderr = stderr_path.read_text(encoding="utf-8")

    assert completed.returncode == 0, stderr
    assert "--source-artifact" in stdout
