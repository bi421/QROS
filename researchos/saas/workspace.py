"""Tenant workspace provisioning boundary for the first authenticated user."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol
from uuid import UUID, uuid4

from researchos.saas.contracts import Plan, WorkspaceRole


@dataclass(frozen=True)
class WorkspaceProvisioningResult:
    workspace_id: UUID
    role: WorkspaceRole
    plan: Plan


class WorkspaceProvisioningConflict(RuntimeError):
    """The authenticated user already has an onboarding workspace."""


class WorkspaceProvisioner(Protocol):
    def provision(self, user_id: UUID, name: str) -> WorkspaceProvisioningResult:
        """Atomically provision the caller's first workspace and entitlement."""


class InMemoryWorkspaceProvisioner:
    """Development/test implementation of first-workspace provisioning."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._owners: dict[UUID, WorkspaceProvisioningResult] = {}
        self._names: dict[UUID, str] = {}

    def provision(self, user_id: UUID, name: str) -> WorkspaceProvisioningResult:
        normalized = name.strip()
        if not normalized:
            raise ValueError("workspace name must not be empty")
        with self._lock:
            if user_id in self._owners:
                raise WorkspaceProvisioningConflict("workspace already provisioned")
            result = WorkspaceProvisioningResult(
                workspace_id=uuid4(), role=WorkspaceRole.OWNER, plan=Plan.FREE
            )
            self._owners[user_id] = result
            self._names[result.workspace_id] = normalized
            return result


@dataclass(frozen=True)
class SupabaseWorkspaceProvisioner:
    """Server-side adapter for the atomic workspace provisioning RPC."""

    supabase_client: Any

    def provision(self, user_id: UUID, name: str) -> WorkspaceProvisioningResult:
        try:
            result = self.supabase_client.rpc(
                "provision_workspace",
                {"p_user_id": str(user_id), "p_name": name},
            ).execute()
        except Exception as exc:
            if "workspace already provisioned" in str(exc):
                raise WorkspaceProvisioningConflict("workspace already provisioned") from exc
            raise RuntimeError("workspace provisioning RPC failed") from exc
        rows = result.data or []
        if len(rows) != 1 or not isinstance(rows[0], dict):
            raise RuntimeError("workspace provisioning RPC returned no unique result")
        row = rows[0]
        try:
            return WorkspaceProvisioningResult(
                workspace_id=UUID(str(row["workspace_id"])),
                role=WorkspaceRole(str(row["role"])),
                plan=Plan(str(row["plan"])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("workspace provisioning RPC returned invalid state") from exc


__all__ = [
    "InMemoryWorkspaceProvisioner",
    "SupabaseWorkspaceProvisioner",
    "WorkspaceProvisioningConflict",
    "WorkspaceProvisioningResult",
    "WorkspaceProvisioner",
]
