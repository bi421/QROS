from __future__ import annotations
import pytest
from scripts.propose_ci_repair import propose

def classification(category: str, repairable: bool = True, evidence: list[str] | None = None) -> dict[str, object]:
    return {"category": category, "confidence": "high", "repairable": repairable, "evidence": evidence if evidence is not None else ["matched signature"]}

def test_repairable_category_is_proposal_only() -> None:
    result = propose(classification("formatting/static failure"))
    assert result.action == "propose-only"
    assert result.allowed is True
    assert result.attempt_limit == 1

def test_non_repairable_category_stops() -> None:
    result = propose(classification("CI orchestration failure", repairable=False))
    assert result.action == "stop"
    assert result.allowed is False

def test_unknown_category_stops() -> None:
    result = propose(classification("future category"))
    assert result.action == "stop"
    assert result.allowed is False

def test_missing_evidence_stops() -> None:
    result = propose({"category": "implementation defect", "repairable": True, "evidence": None})
    assert result.action == "stop"
    assert result.allowed is False

def test_zero_attempt_limit_stops() -> None:
    result = propose(classification("test/contract mismatch"), attempt_limit=0)
    assert result.action == "stop"
    assert result.allowed is False

def test_negative_attempt_limit_is_rejected() -> None:
    with pytest.raises(ValueError):
        propose(classification("implementation defect"), attempt_limit=-1)
