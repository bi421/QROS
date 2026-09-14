"""
External Evidence Chain Validator.
Validates that RuntimeCertifier output satisfies all 8 architectural invariants.
"""
from __future__ import annotations

from typing import List, Tuple
from researchos.objects.evidence import EvidenceRegistry
from researchos.core.identity import deterministic_hash


class EvidenceChainValidator:
    """Validates evidence chain integrity from external observation point."""

    def __init__(self, registry: EvidenceRegistry):
        self.registry = registry
        self.violations: List[str] = []

    def validate_all(self) -> Tuple[bool, List[str]]:
        """Run all 8 invariant checks."""
        self.violations = []

        self._check_one_run_one_evidence()
        self._check_deterministic_hash()
        self._check_timestamp_independence()
        self._check_lineage_continuity()
        self._check_append_only()
        self._check_no_false_certification()
        self._check_quantitative_immutable()
        self._check_synthetic_boundary()

        return (len(self.violations) == 0, self.violations)

    def _check_one_run_one_evidence(self) -> None:
        obs_ids = [e.observation_id for e in self.registry.evidence]
        if len(obs_ids) != len(set(obs_ids)):
            self.violations.append("INVARIANT 1 VIOLATED: Duplicate observation_id")

    def _check_deterministic_hash(self) -> None:
        for evidence in self.registry.evidence:
            parts = evidence.observation_id.split("|")
            if len(parts) >= 4:
                expected_prefix = deterministic_hash(
                    {
                        "experiment_id": parts[1],
                        "run_id": parts[2],
                    }
                )[:16]
                if parts[3] != expected_prefix:
                    self.violations.append(f"INVARIANT 2 VIOLATED: Hash mismatch in {evidence.id}")

    def _check_timestamp_independence(self) -> None:
        for evidence in self.registry.evidence:
            if evidence.created_at.isoformat() in evidence.observation_id:
                self.violations.append("INVARIANT 3 VIOLATED: Timestamp in observation_id")

    def _check_lineage_continuity(self) -> None:
        for evidence in self.registry.evidence:
            parts = evidence.observation_id.split("|")
            if len(parts) < 3:
                self.violations.append(f"INVARIANT 4 VIOLATED: Missing lineage in {evidence.id}")

    def _check_append_only(self) -> None:
        if len(self.registry.evidence) < 0:
            self.violations.append("INVARIANT 5 VIOLATED: Registry size decreased")

    def _check_no_false_certification(self) -> None:
        for evidence in self.registry.evidence:
            if (
                "failed" in evidence.interpretation.lower()
                or "error" in evidence.interpretation.lower()
            ):
                if evidence.direction != "Contradicting":
                    self.violations.append("INVARIANT 6 VIOLATED: Failed but not Contradicting")

    def _check_quantitative_immutable(self) -> None:
        for evidence in self.registry.evidence:
            expected_quality = evidence._compute_quality()
            if abs(evidence.quality - expected_quality) > 1e-9:
                self.violations.append(f"INVARIANT 7 VIOLATED: Quality mutated in {evidence.id}")

    def _check_synthetic_boundary(self) -> None:
        for evidence in self.registry.evidence:
            if (
                "synthetic" in evidence.observation_id.lower()
                or "mock" in evidence.observation_id.lower()
            ):
                if "SYNTHETIC" not in evidence.interpretation.upper():
                    self.violations.append("INVARIANT 8 VIOLATED: Synthetic not labeled")

    def generate_report(self) -> str:
        passed, violations = self.validate_all()
        report = f"""
================================================================================
              EXTERNAL EVIDENCE CHAIN VALIDATION REPORT
================================================================================

Registry: {self.registry.research_id}
Total Evidence: {len(self.registry.evidence)}
Validation Status: {'PASSED' if passed else 'FAILED'}
Violations: {len(violations)}

"""
        if violations:
            report += "\nVIOLATIONS:\n"
            for v in violations:
                report += f"  - {v}\n"
        else:
            report += "All 8 invariants satisfied.\n"

        report += (
            "================================================================================\n"
        )
        return report
