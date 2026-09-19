from datetime import datetime, timedelta, timezone

import pytest

from researchos.saas.retention import (
    DeletionCandidate,
    RetentionDecision,
    RetentionPolicy,
    evaluate_deletion,
)


NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def candidate(**overrides: object) -> DeletionCandidate:
    values: dict[str, object] = {
        "resource_type": "artifact",
        "resource_id": "artifact-1",
        "created_at": NOW - timedelta(days=31),
    }
    values.update(overrides)
    return DeletionCandidate(**values)  # type: ignore[arg-type]


def test_expired_unreferenced_resource_is_eligible() -> None:
    decision, reason = evaluate_deletion(candidate(), now=NOW)
    assert decision is RetentionDecision.ELIGIBLE
    assert reason == "retention_window_elapsed"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"created_at": NOW - timedelta(days=29)}, "retention_window_active"),
        ({"reference_count": 1}, "active_references"),
        ({"legal_hold": True}, "legal_hold"),
        ({"resource_type": "research_claim"}, "resource_type_not_deletable"),
    ],
)
def test_safety_conditions_fail_closed(
    overrides: dict[str, object], reason: str
) -> None:
    decision, actual_reason = evaluate_deletion(candidate(**overrides), now=NOW)
    assert decision is RetentionDecision.RETAIN
    assert actual_reason == reason


def test_custom_policy_controls_retention_window_and_resource_types() -> None:
    policy = RetentionPolicy(
        min_age=timedelta(days=7),
        deletable_resource_types=frozenset({"dataset"}),
    )
    decision, reason = policy.evaluate(
        candidate(resource_type="dataset", created_at=NOW - timedelta(days=8)),
        now=NOW,
    )
    assert decision is RetentionDecision.ELIGIBLE
    assert reason == "retention_window_elapsed"


def test_candidate_rejects_negative_reference_count() -> None:
    with pytest.raises(ValueError, match="reference_count"):
        candidate(reference_count=-1)


def test_candidate_and_now_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        DeletionCandidate(
            resource_type="artifact",
            resource_id="artifact-1",
            created_at=datetime(2026, 9, 19),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate_deletion(candidate(), now=datetime(2026, 9, 19))



def test_executor_requires_approval_audit_and_delete_before_destructive_action() -> None:
    from researchos.saas.retention import execute_deletion

    calls: list[str] = []
    base = {"approved": True, "authorize": lambda _candidate: True, "dependency_check": lambda _candidate: True}
    for kwargs, reason in [
        ({}, "approval_required"),
        ({**base}, "audit_sink_required"),
        ({**base, "audit": lambda *_: calls.append("audit")}, "delete_operation_required"),
    ]:
        result = execute_deletion(candidate(), now=NOW, **kwargs)
        assert result.deleted is False
        assert result.reason == reason
        assert calls == []


def test_executor_audits_before_and_after_successful_delete() -> None:
    from researchos.saas.retention import execute_deletion

    calls: list[str] = []
    result = execute_deletion(
        candidate(),
        now=NOW,
        approved=True,
        authorize=lambda _candidate: True,
        dependency_check=lambda _candidate: True,
        audit=lambda _candidate, event: calls.append(event),
        delete=lambda _candidate: calls.append("delete"),
    )
    assert result.deleted is True
    assert result.reason == "deletion_completed"
    assert calls == ["deletion_approved", "delete", "deletion_completed"]


def test_executor_does_not_delete_when_pre_delete_audit_fails() -> None:
    from researchos.saas.retention import execute_deletion

    calls: list[str] = []

    def audit(_candidate, event):
        calls.append(event)
        raise RuntimeError("audit unavailable")

    with pytest.raises(RuntimeError, match="audit unavailable"):
        execute_deletion(
            candidate(),
            now=NOW,
            approved=True,
            authorize=lambda _candidate: True,
            dependency_check=lambda _candidate: True,
            audit=audit,
            delete=lambda _candidate: calls.append("delete"),
        )
    assert calls == ["deletion_approved"]


def test_executor_never_calls_delete_for_ineligible_candidate() -> None:
    from researchos.saas.retention import execute_deletion

    calls: list[str] = []
    result = execute_deletion(
        candidate(reference_count=1),
        now=NOW,
        approved=True,
        authorize=lambda _candidate: True,
        dependency_check=lambda _candidate: True,
        audit=lambda *_: calls.append("audit"),
        delete=lambda _candidate: calls.append("delete"),
    )
    assert result.deleted is False
    assert result.reason == "active_references"
    assert calls == []

def test_executor_requires_authorization_and_dependency_resolution() -> None:
    from researchos.saas.retention import execute_deletion

    result = execute_deletion(candidate(), now=NOW, approved=True)
    assert result.reason == "tenant_authorization_required"

    result = execute_deletion(
        candidate(),
        now=NOW,
        approved=True,
        authorize=lambda _candidate: False,
    )
    assert result.reason == "tenant_authorization_denied"

    result = execute_deletion(
        candidate(),
        now=NOW,
        approved=True,
        authorize=lambda _candidate: True,
    )
    assert result.reason == "dependency_check_required"

    result = execute_deletion(
        candidate(),
        now=NOW,
        approved=True,
        authorize=lambda _candidate: True,
        dependency_check=lambda _candidate: False,
    )
    assert result.reason == "active_dependencies"
