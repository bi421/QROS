"""
Synthetic-Data Boundary Enforcer.
"""
from __future__ import annotations

from typing import Set
from researchos.objects.evidence import Evidence, EvidenceRegistry


class SyntheticBoundaryChecker:
    """Enforces hard boundary between synthetic and real data."""

    SYNTHETIC_MARKERS: Set[str] = {"SYNTHETIC", "MOCK", "TEST", "PLACEHOLDER"}

    def __init__(self, registry: EvidenceRegistry):
        self.registry = registry

    def classify_evidence(self, evidence: Evidence) -> str:
        obs_id_upper = evidence.observation_id.upper()
        interp_upper = evidence.interpretation.upper()

        for marker in self.SYNTHETIC_MARKERS:
            if marker in obs_id_upper or marker in interp_upper:
                return "SYNTHETIC"

        return "REAL"

    def validate_no_mixing(self) -> bool:
        synthetic_count = sum(1 for e in self.registry.evidence if self.classify_evidence(e) == "SYNTHETIC")
        real_count = len(self.registry.evidence) - synthetic_count

        if synthetic_count > 0 and real_count > 0:
            return False

        return True

    def generate_report(self) -> str:
        synthetic_count = sum(1 for e in self.registry.evidence if self.classify_evidence(e) == "SYNTHETIC")
        real_count = len(self.registry.evidence) - synthetic_count
        boundary_ok = self.validate_no_mixing()

        report = f"""
================================================================================
              SYNTHETIC-DATA BOUNDARY VALIDATION REPORT
================================================================================

Registry: {self.registry.research_id}
Total Evidence: {len(self.registry.evidence)}
  Synthetic: {synthetic_count}
  Real: {real_count}

Boundary Status: {'PASSED (no mixing)' if boundary_ok else 'FAILED (mixed)'}

================================================================================
"""
        return report
