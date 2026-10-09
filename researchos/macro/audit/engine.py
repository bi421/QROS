"""
ResearchOS Macro Intelligence Layer - Audit Engine
Version: audit/engine/v1
Status: FROZEN
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from researchos.macro.audit.log import AuditEntry, AuditLog, IntegrityCheck
from researchos.macro.revision.enums import IntegrityLevel
from researchos.macro.revision.record import RevisionChain, RevisionRecord


@dataclass(frozen=True)
class AuditResult:
    """
    Result of an audit operation.
    """

    audit_id: str
    timestamp: datetime
    object_type: str
    object_id: str

    # Results
    passed: bool
    checks_performed: int
    checks_passed: int
    checks_failed: int

    # Revision tracking
    revision_id: str | None = None

    # Details
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Generated
    version: str = "audit/engine/v1"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "audit_id": self.audit_id,
            "timestamp": self.timestamp.isoformat(),
            "object_type": self.object_type,
            "object_id": self.object_id,
            "revision_id": self.revision_id,
            "passed": self.passed,
            "checks_performed": self.checks_performed,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "errors": self.errors,
            "warnings": self.warnings,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditResult:
        """Deserialize from dictionary."""
        return cls(
            audit_id=data["audit_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            object_type=data["object_type"],
            object_id=data["object_id"],
            revision_id=data.get("revision_id"),
            passed=data["passed"],
            checks_performed=data["checks_performed"],
            checks_passed=data["checks_passed"],
            checks_failed=data["checks_failed"],
            errors=data.get("errors", []),
            warnings=data.get("warnings", []),
            version=data.get("version", "audit/engine/v1"),
        )


class AuditEngine:
    """
    Engine for performing audits on macro objects.

    Provides:
    - Historical reconstruction
    - Lineage tracing
    - Integrity verification
    - Audit log management
    """

    def __init__(self):
        self.audit_log = AuditLog(log_id="AUDIT_LOG_001")

    def audit_revision(
        self,
        revision: RevisionRecord,
        level: IntegrityLevel = IntegrityLevel.STANDARD,
    ) -> AuditResult:
        """
        Audit a revision record.

        Checks:
        - Revision ID format
        - Object ID format
        - Timestamp ordering
        - Lineage integrity
        - Provenance completeness
        """
        errors = []
        warnings = []
        checks_performed = 0
        checks_passed = 0

        # Check 1: Revision ID format
        checks_performed += 1
        if revision.revision_id.startswith("REV_"):
            checks_passed += 1
        else:
            errors.append("Invalid revision_id format")

        # Check 2: Object ID format
        checks_performed += 1
        valid_prefixes = ("SER_", "EV_", "EVNT_", "KN_")
        if any(revision.object_id.startswith(prefix) for prefix in valid_prefixes):
            checks_passed += 1
        else:
            errors.append("Invalid object_id format")

        # Check 3: Timestamp ordering
        checks_performed += 1
        if revision.effective_from <= revision.created_at:
            checks_passed += 1
        else:
            errors.append("effective_from cannot be after created_at")

        # Check 4: No circular lineage
        checks_performed += 1
        if revision.parent_revision_id != revision.revision_id:
            checks_passed += 1
        else:
            errors.append("Circular lineage detected")

        # Check 5: Provenance completeness
        checks_performed += 1
        if revision.provenance:
            prov_valid, prov_errors = revision.provenance.validate()
            if prov_valid:
                checks_passed += 1
            else:
                errors.extend(prov_errors)
        else:
            warnings.append("No provenance chain attached")
            checks_passed += 1  # Provenance is optional

        passed = len(errors) == 0

        result = AuditResult(
            audit_id=f"AUDIT_{revision.revision_id}",
            timestamp=datetime.now(timezone.utc),
            object_type=revision.object_type,
            object_id=revision.object_id,
            revision_id=revision.revision_id,
            passed=passed,
            checks_performed=checks_performed,
            checks_passed=checks_passed,
            checks_failed=checks_performed - checks_passed,
            errors=errors,
            warnings=warnings,
        )

        # Log the audit
        entry = AuditEntry(
            audit_id=f"AUDIT_LOG_{revision.revision_id}",
            timestamp=result.timestamp,
            action=type("obj", (object,), {"value": "audit"})(),
            object_type=revision.object_type,
            object_id=revision.object_id,
            revision_id=revision.revision_id,
            actor="audit_engine",
            details={"level": level.value, "checks_performed": checks_performed},
            success=passed,
        )
        self.audit_log = self.audit_log.add_entry(entry)

        return result

    def audit_revision_chain(
        self,
        chain: RevisionChain,
        level: IntegrityLevel = IntegrityLevel.STANDARD,
    ) -> AuditResult:
        """
        Audit a complete revision chain.

        Checks:
        - Revision continuity
        - No missing revisions
        - No duplicate revisions
        - Valid lineage
        - Complete provenance
        """
        errors = []
        warnings = []
        checks_performed = 0
        checks_passed = 0

        # Check 1: Chain has at least one revision
        checks_performed += 1
        if len(chain.revisions) >= 1:
            checks_passed += 1
        else:
            errors.append("Revision chain is empty")

        # Check 2: Revisions are numbered sequentially
        checks_performed += 1
        revision_numbers = [r.revision_number for r in chain.revisions]
        if revision_numbers == list(range(1, len(revision_numbers) + 1)):
            checks_passed += 1
        else:
            errors.append("Revision numbers are not sequential")

        # Check 3: No duplicate revisions
        checks_performed += 1
        if len(revision_numbers) == len(set(revision_numbers)):
            checks_passed += 1
        else:
            errors.append("Duplicate revision numbers detected")

        # Check 4: No circular references
        checks_performed += 1
        try:
            chain._verify_no_cycles()
            checks_passed += 1
        except ValueError as e:
            errors.append(str(e))

        # Check 5: Lineage is complete
        checks_performed += 1
        lineage_valid = True
        for rev in chain.revisions:
            if rev.parent_revision_id:
                # Parent should exist
                parent_exists = any(r.revision_id == rev.parent_revision_id for r in chain.revisions)
                if not parent_exists:
                    lineage_valid = False
                    errors.append(f"Missing parent revision: {rev.parent_revision_id}")

        if lineage_valid:
            checks_passed += 1

        passed = len(errors) == 0

        result = AuditResult(
            audit_id=f"AUDIT_CHAIN_{chain.object_id}",
            timestamp=datetime.now(timezone.utc),
            object_type=chain.object_type,
            object_id=chain.object_id,
            passed=passed,
            checks_performed=checks_performed,
            checks_passed=checks_passed,
            checks_failed=checks_performed - checks_passed,
            errors=errors,
            warnings=warnings,
        )

        return result

    def reconstruct_history(
        self,
        chain: RevisionChain,
        target_revision_number: int,
    ) -> RevisionRecord | None:
        """
        Reconstruct historical state at a specific revision.

        MIL-AUDIT-001: Historical reconstruction must be deterministic.
        """
        revision = chain.get_revision(target_revision_number)
        if revision:
            # Log the reconstruction
            entry = AuditEntry(
                audit_id=f"AUDIT_RECONSTRUCT_{chain.object_id}_{target_revision_number}",
                timestamp=datetime.now(timezone.utc),
                action=type("obj", (object,), {"value": "reconstruct"})(),
                object_type=chain.object_type,
                object_id=chain.object_id,
                revision_id=str(target_revision_number),
                actor="audit_engine",
                details={"target_revision": target_revision_number},
                success=True,
            )
            self.audit_log = self.audit_log.add_entry(entry)

        return revision

    def verify_integrity(
        self,
        chain: RevisionChain,
        level: IntegrityLevel = IntegrityLevel.STANDARD,
    ) -> IntegrityCheck:
        """
        Perform integrity verification on a revision chain.
        """
        checks_performed = []
        checks_passed = []
        checks_failed = []
        error_details = []
        warnings = []

        # Basic integrity checks
        checks_performed.append("revision_count")
        if len(chain.revisions) >= 1:
            checks_passed.append("revision_count")
        else:
            checks_failed.append("revision_count")
            error_details.append("Empty revision chain")

        checks_performed.append("sequential_numbers")
        revision_numbers = [r.revision_number for r in chain.revisions]
        if revision_numbers == list(range(1, len(revision_numbers) + 1)):
            checks_passed.append("sequential_numbers")
        else:
            checks_failed.append("sequential_numbers")
            error_details.append("Non-sequential revision numbers")

        checks_performed.append("no_duplicates")
        if len(revision_numbers) == len(set(revision_numbers)):
            checks_passed.append("no_duplicates")
        else:
            checks_failed.append("no_duplicates")
            error_details.append("Duplicate revision numbers")

        checks_performed.append("no_cycles")
        try:
            chain._verify_no_cycles()
            checks_passed.append("no_cycles")
        except ValueError:
            checks_failed.append("no_cycles")
            error_details.append("Circular reference detected")

        passed = len(checks_failed) == 0

        check = IntegrityCheck(
            check_id=f"CHECK_{chain.object_id}",
            timestamp=datetime.now(timezone.utc),
            object_type=chain.object_type,
            object_id=chain.object_id,
            revision_id=None,
            level=level,
            passed=passed,
            checks_performed=checks_performed,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            error_details=error_details,
            warnings=warnings,
        )

        # Log the check
        entry = AuditEntry(
            audit_id=f"AUDIT_CHECK_{chain.object_id}",
            timestamp=check.timestamp,
            action=type("obj", (object,), {"value": "verify"})(),
            object_type=chain.object_type,
            object_id=chain.object_id,
            revision_id=None,
            actor="audit_engine",
            details={"level": level.value, "passed": passed},
            success=passed,
        )
        self.audit_log = self.audit_log.add_entry(entry)

        return check
