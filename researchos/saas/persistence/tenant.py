"""Tenant-scoped retention, soft deletion, and GDPR export contracts."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

DEFAULT_RETENTION_DAYS = 30


class TenantPersistenceError(RuntimeError):
    """Raised when a tenant lifecycle operation cannot be completed."""


@dataclass(frozen=True)
class RetentionConfig:
    retention_days: int = DEFAULT_RETENTION_DAYS

    def __post_init__(self) -> None:
        if not 1 <= self.retention_days <= 3650:
            raise ValueError("retention_days must be between 1 and 3650 days")

    def purge_at(self, deleted_at: datetime) -> datetime:
        if deleted_at.tzinfo is None or deleted_at.utcoffset() is None:
            raise ValueError("deleted_at must be timezone-aware")
        return deleted_at + timedelta(days=self.retention_days)


@dataclass(frozen=True)
class DeletionReceipt:
    workspace_id: UUID
    deleted_at: datetime
    scheduled_purge_at: datetime
    retention_days: int
    receipt_id: UUID = field(default_factory=uuid4)


class TenantPersistence(Protocol):
    def is_workspace_deleted(self, workspace_id: UUID) -> bool:
        ...

    def soft_delete_workspace(
        self,
        workspace_id: UUID,
        *,
        retention: RetentionConfig | None = None,
        deleted_at: datetime | None = None,
    ) -> DeletionReceipt:
        ...

    def export_workspace(self, workspace_id: UUID) -> bytes:
        ...

    def hard_purge_expired(self, *, now: datetime | None = None) -> int:
        ...


def _historical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_export_zip(
    *,
    workspace_id: UUID,
    datasets: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    evidence_envelopes: list[dict[str, Any]],
    additional: dict[str, list[dict[str, Any]]] | None = None,
) -> bytes:
    """Build a deterministic machine-readable tenant export.

    Deleted rows are intentionally included: an export is a data-access
    artifact, not a list view, and therefore preserves the tenant's lifecycle
    history until the scheduled purge.
    """
    payloads: dict[str, object] = {
        "manifest.json": {
            "schema": "qros.tenant-export.v1",
            "workspace_id": str(workspace_id),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "datasets_count": len(datasets),
            "jobs_count": len(jobs),
            "evidence_envelopes_count": len(evidence_envelopes),
        },
        "datasets.json": datasets,
        "jobs.json": jobs,
        "evidence_envelopes.json": evidence_envelopes,
    }
    for name, rows in (additional or {}).items():
        payloads[f"{name}.json"] = rows

    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name in sorted(payloads):
            archive.writestr(
                name,
                json.dumps(
                    payloads[name],
                    sort_keys=True,
                    indent=2,
                    default=str,
                ).encode("utf-8"),
            )
    return output.getvalue()


@dataclass
class _TenantRow:
    table: str
    row_id: str
    workspace_id: UUID
    payload: dict[str, Any]
    deleted_at: datetime | None = None
    historical_hash: str | None = None


class InMemoryTenantPersistence:
    """Deterministic lifecycle implementation used by API contract tests."""

    def __init__(self) -> None:
        self._rows: list[_TenantRow] = []
        self._receipts: dict[UUID, DeletionReceipt] = {}

    def is_workspace_deleted(self, workspace_id: UUID) -> bool:
        receipt = self._receipts.get(workspace_id)
        return receipt is not None

    def add(self, table: str, row_id: str, workspace_id: UUID, payload: dict[str, Any]) -> None:
        self._rows.append(
            _TenantRow(
                table=table,
                row_id=row_id,
                workspace_id=workspace_id,
                payload=dict(payload),
            )
        )

    def visible(self, table: str, workspace_id: UUID) -> list[dict[str, Any]]:
        return [
            dict(row.payload)
            for row in self._rows
            if row.table == table
            and row.workspace_id == workspace_id
            and row.deleted_at is None
        ]

    def soft_delete_workspace(
        self,
        workspace_id: UUID,
        *,
        retention: RetentionConfig | None = None,
        deleted_at: datetime | None = None,
    ) -> DeletionReceipt:
        policy = retention or RetentionConfig()
        deleted = deleted_at or datetime.now(timezone.utc)
        if deleted.tzinfo is None or deleted.utcoffset() is None:
            raise ValueError("deleted_at must be timezone-aware")

        for row in self._rows:
            if row.workspace_id != workspace_id or row.deleted_at is not None:
                continue
            row.deleted_at = deleted
            row.historical_hash = _historical_hash(row.payload)

        receipt = DeletionReceipt(
            workspace_id=workspace_id,
            deleted_at=deleted,
            scheduled_purge_at=policy.purge_at(deleted),
            retention_days=policy.retention_days,
        )
        self._receipts[workspace_id] = receipt
        return receipt

    def hard_purge_expired(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(timezone.utc)
        expired = [workspace_id for workspace_id, receipt in self._receipts.items() if receipt.scheduled_purge_at <= current]
        if not expired:
            return 0
        self._rows = [row for row in self._rows if row.workspace_id not in expired]
        for workspace_id in expired:
            self._receipts.pop(workspace_id, None)
        return len(expired)

    def export_workspace(self, workspace_id: UUID) -> bytes:
        rows = [row for row in self._rows if row.workspace_id == workspace_id]

        def records(table: str) -> list[dict[str, Any]]:
            return [
                {
                    **row.payload,
                    "deleted_at": row.deleted_at,
                    "historical_hash": row.historical_hash,
                }
                for row in rows
                if row.table == table
            ]

        return build_export_zip(
            workspace_id=workspace_id,
            datasets=records("dataset"),
            jobs=records("research_run"),
            evidence_envelopes=records("evidence"),
            additional={
                "dataset_versions": records("dataset_version"),
                "artifacts": records("artifact"),
                "research_claims": records("research_claim"),
                "research_validation": records("research_validation"),
                "research_findings": records("research_finding"),
                "audit_events": records("audit_event"),
            },
        )


__all__ = [
    "DEFAULT_RETENTION_DAYS",
    "DeletionReceipt",
    "InMemoryTenantPersistence",
    "RetentionConfig",
    "TenantPersistence",
    "TenantPersistenceError",
    "build_export_zip",
]
