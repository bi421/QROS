import pytest

from researchos.research_core.validation_state import (
    OOSState,
    ReplicationState,
    transition_oos,
    transition_replication,
)


def test_oos_requires_pending_before_terminal_state():
    assert transition_oos(OOSState.NOT_APPLICABLE, OOSState.PENDING) is OOSState.PENDING
    assert transition_oos(OOSState.PENDING, OOSState.PASS) is OOSState.PASS
    assert transition_oos(OOSState.PENDING, OOSState.FAIL) is OOSState.FAIL


def test_oos_terminal_states_are_immutable():
    with pytest.raises(ValueError):
        transition_oos(OOSState.PASS, OOSState.PENDING)
    with pytest.raises(ValueError):
        transition_oos(OOSState.FAIL, OOSState.PASS)


def test_replication_follows_same_governance():
    assert transition_replication(ReplicationState.NOT_APPLICABLE, ReplicationState.PENDING) is ReplicationState.PENDING
    assert transition_replication(ReplicationState.PENDING, ReplicationState.PASS) is ReplicationState.PASS
    with pytest.raises(ValueError):
        transition_replication(ReplicationState.PASS, ReplicationState.FAIL)
