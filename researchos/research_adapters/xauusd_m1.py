"""Bind the frozen XAUUSD M1 pipeline to the application-neutral core.

This module is deliberately outside ``research_core``.  It knows how to resolve
raw dataset bytes and how to call the existing frozen research stages; the core
only receives immutable contracts and content-addressed output metadata.
"""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from researchos.research_core.contracts import ResearchRequest
from researchos.research_core.runner import PipelineArtifact
from scripts.run_xauusd_m1_oos_calibration import run as run_calibration
from scripts.run_xauusd_m1_real_pipeline import run as run_real_pipeline
from scripts.run_xauusd_m1_walkforward import run as run_walkforward


class RawDatasetResolver(Protocol):
    """Resolve the exact raw bytes identified by a ResearchDataset."""

    def __call__(self, request: ResearchRequest) -> bytes:
        """Return raw dataset bytes for the requested dataset."""


class FrozenXauusdM1Pipeline:
    """Execute the existing frozen XAUUSD M1 stages without changing them."""

    def __init__(self, resolver: RawDatasetResolver) -> None:
        self._resolver = resolver

    def __call__(self, request: ResearchRequest) -> Iterable[PipelineArtifact]:
        raw = self._resolver(request)
        actual_sha256 = hashlib.sha256(raw).hexdigest()
        if actual_sha256 != request.dataset.content_sha256:
            raise ValueError(
                "resolved raw dataset SHA-256 does not match the ResearchDataset provenance"
            )

        with tempfile.TemporaryDirectory(prefix="researchos-xauusd-m1-") as temp_dir:
            root = Path(temp_dir)
            source_path = root / "xauusd_m1_mt5.csv"
            real_path = root / "xauusd_m1_real_events_outcomes.json"
            walkforward_path = root / "xauusd_m1_walkforward.json"
            calibration_path = root / "xauusd_m1_oos_calibration.json"
            source_path.write_bytes(raw)

            run_real_pipeline(source_path, real_path, threshold=0.0)
            run_walkforward(
                real_path,
                walkforward_path,
                train_size=2000,
                validation_size=500,
                step_size=500,
            )
            run_calibration(real_path, walkforward_path, calibration_path)

            outputs = (
                ("xauusd_m1_real_events", real_path),
                ("xauusd_m1_walkforward", walkforward_path),
                ("xauusd_m1_oos_calibration", calibration_path),
            )
            for kind, path in outputs:
                content = path.read_bytes()
                yield PipelineArtifact(
                    artifact_id=hashlib.sha256(content).hexdigest(),
                    kind=kind,
                    content=content,
                )


__all__ = ["FrozenXauusdM1Pipeline", "RawDatasetResolver"]
