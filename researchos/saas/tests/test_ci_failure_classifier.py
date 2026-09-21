from __future__ import annotations

from scripts.classify_ci_failure import classify


def test_ci_orchestration_is_not_repairable() -> None:
    result = classify("workflow completed with failure; total_count: 0; jobs: []")
    assert result.category == "CI orchestration failure"
    assert result.repairable is False


def test_empty_log_fails_closed() -> None:
    result = classify("")
    assert result.category == "ambiguous/unsafe"
    assert result.repairable is False


def test_static_failure_is_repairable() -> None:
    result = classify("ruff check failed: W292 no newline at end of file")
    assert result.category == "formatting/static failure"
    assert result.repairable is True


def test_environment_failure_is_repairable() -> None:
    result = classify("pip install failed: temporary failure in name resolution")
    assert result.category == "environment/tooling failure"
    assert result.repairable is True


def test_missing_prerequisite_is_repairable() -> None:
    result = classify("required secret DATABASE_URL is missing")
    assert result.category == "missing prerequisite"
    assert result.repairable is True


def test_test_contract_failure_is_repairable() -> None:
    result = classify("test_contract.py::test_expected failed: AssertionError")
    assert result.category == "test/contract mismatch"
    assert result.repairable is True


def test_implementation_failure_is_repairable() -> None:
    result = classify("Traceback (most recent call last):\n  File 'api.py', line 42\nValueError")
    assert result.category == "implementation defect"
    assert result.repairable is True


def test_conflicting_signals_fail_closed() -> None:
    result = classify("ruff check failed and AssertionError in test_contract.py")
    assert result.category == "ambiguous/unsafe"
    assert result.repairable is False


def test_unknown_failure_fails_closed() -> None:
    result = classify("CI failed for an unknown reason")
    assert result.category == "ambiguous/unsafe"
    assert result.repairable is False


def test_evidence_is_machine_readable() -> None:
    result = classify("ruff check failed: E501")
    assert result.evidence
    assert all(isinstance(item, str) for item in result.evidence)
