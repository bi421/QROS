"""Governed OOS and replication state contracts."""

from __future__ import annotations

from enum import Enum


class OOSState(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"


class ReplicationState(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"


_ALLOWED_OOS = {
    OOSState.NOT_APPLICABLE: {OOSState.NOT_APPLICABLE, OOSState.PENDING},
    OOSState.PENDING: {OOSState.PENDING, OOSState.PASS, OOSState.FAIL},
    OOSState.PASS: {OOSState.PASS},
    OOSState.FAIL: {OOSState.FAIL},
}
_ALLOWED_REPLICATION = {
    ReplicationState.NOT_APPLICABLE: {ReplicationState.NOT_APPLICABLE, ReplicationState.PENDING},
    ReplicationState.PENDING: {ReplicationState.PENDING, ReplicationState.PASS, ReplicationState.FAIL},
    ReplicationState.PASS: {ReplicationState.PASS},
    ReplicationState.FAIL: {ReplicationState.FAIL},
}


def transition_oos(current: OOSState | str, target: OOSState | str) -> OOSState:
    current, target = OOSState(current), OOSState(target)
    if target not in _ALLOWED_OOS[current]:
        raise ValueError(f"invalid OOS transition: {current.value} -> {target.value}")
    return target


def transition_replication(current: ReplicationState | str, target: ReplicationState | str) -> ReplicationState:
    current, target = ReplicationState(current), ReplicationState(target)
    if target not in _ALLOWED_REPLICATION[current]:
        raise ValueError(f"invalid replication transition: {current.value} -> {target.value}")
    return target


__all__ = ["OOSState", "ReplicationState", "transition_oos", "transition_replication"]
