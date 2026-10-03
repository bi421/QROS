"""
Runtime Evidence Certification Engine.
Wires the experiment execution path to the EvidenceRepository with strict determinism.
Guarantees:
1. Deterministic artifact identity (no runtime timestamps in hash).
2. Explicit parent/child lineage.
3. Append-only persistence.
"""
from __future__ import annotations

from typing import Any, Dict
from researchos.core.identity import deterministic_hash
from researchos.objects.evidence import Evidence, EvidenceRegistry


class RuntimeCertifier:
    """Certifies experiment results and appends them to the evidence registry."""

    def __init__(self, registry: EvidenceRegistry):
        self.registry = registry

    def certify_run(
        self,
        experiment_id: str,
        run_id: str,
        result_data: Dict[str, Any],
        hypothesis_id: str,
        interpretation: str,
        direction: str = "Neutral",
    ) -> Evidence:
        # 1. Deterministic Artifact Identity (Exclude runtime telemetry)
        hash_payload = {
            "experiment_id": experiment_id,
            "run_id": run_id,
            "result_data": result_data,
            "hypothesis_id": hypothesis_id,
        }
        artifact_hash = deterministic_hash(hash_payload)

        # 2. Explicit Lineage in Observation ID
        observation_id = f"OBS|{experiment_id}|{run_id}|{artifact_hash[:16]}"

        # 3. Create Evidence Object
        evidence = Evidence(
            observation_id=observation_id,
            hypothesis_id=hypothesis_id,
            interpretation=interpretation,
            direction=direction,
            source_reliability=0.95,
            tier="Primary",
        )

        # 4. Append-only Persistence
        self.registry.add_evidence(evidence)
        return evidence

    def certify_failure(
        self,
        experiment_id: str,
        run_id: str,
        error_message: str,
        hypothesis_id: str,
    ) -> Evidence:
        """Certifies a failed run as contradictory evidence."""
        return self.certify_run(
            experiment_id=experiment_id,
            run_id=run_id,
            result_data={"status": "failed", "error": error_message},
            hypothesis_id=hypothesis_id,
            interpretation=f"Run failed: {error_message}",
            direction="Contradicting",
        )
