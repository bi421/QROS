"""Bind the frozen XAUUSD M1 pipeline to the application-neutral core.

This module is deliberately outside ``research_core``.  It knows how to resolve
raw dataset bytes and how to call the existing frozen research stages; the core
only receives immutable contracts and content-addressed output metadata.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from researchos.research_core.contracts import ResearchRequest
from researchos.research_core.runner import PipelineArtifact
from researchos.evaluation.research_run_metrics import evaluate_xauusd_m1_run
from researchos.orchestration.qros_research_controls import (
    QROS_RESEARCH_CONTROLS_VERSION,
    build_audit_record,
    unified_research_gate,
)
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
            metrics_path = root / "xauusd_m1_meta_evaluation.json"
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

            real_bytes = real_path.read_bytes()
            walkforward_bytes = walkforward_path.read_bytes()
            calibration_bytes = calibration_path.read_bytes()
            real_report = json.loads(real_bytes)
            meta_metrics = evaluate_xauusd_m1_run(real_bytes, walkforward_bytes, calibration_bytes)

            # The frozen M1 workflow currently has no verified spread/commission/slippage
            # evidence. Invoke the gate fail-closed; do not mislabel gross event returns as net.
            cost_metadata = {
                "cost_source": "MT5_SPREAD_COLUMN_IN_FROZEN_DATASET",
                "cost_units": "MT5_NATIVE_SPREAD_POINTS_UNCONVERTED",
                "commission_model": "NOT_CONFIGURED",
                "slippage_model": "NOT_CONFIGURED",
                # The hash identifies the source dataset that contains the spread field;
                # it is not a separately extracted spread-only file.
                "spread_log_sha256": request.dataset.content_sha256,
                "spread_observation_count": int(real_report.get("dataset", {}).get("rows") or 0),
                "net_return_definition": "GROSS_ONLY_COSTS_NOT_APPLIED",
            }
            gate_decision = unified_research_gate(
                trade_returns=None,
                fold_returns=None,
                tested_trial_count=1,
                cost_metadata=cost_metadata,
            )
            meta_metrics["research_controls_version"] = QROS_RESEARCH_CONTROLS_VERSION
            meta_metrics["research_gate"] = gate_decision
            audit_record = build_audit_record(
                input_payload={
                    "dataset_sha256": request.dataset.content_sha256,
                    "dataset_rows_reported_by_engine": real_report.get("dataset", {}).get("rows"),
                    "dataset_row_metadata_count": len(request.dataset.rows),
                    "upstream_artifacts": {
                        "real_events_sha256": hashlib.sha256(real_bytes).hexdigest(),
                        "walkforward_sha256": hashlib.sha256(walkforward_bytes).hexdigest(),
                        "calibration_sha256": hashlib.sha256(calibration_bytes).hexdigest(),
                    },
                },
                decision=gate_decision,
                source_commit=os.environ.get("QROS_SOURCE_COMMIT", "UNDECLARED_RUNTIME_SOURCE_COMMIT"),
                config_version=QROS_RESEARCH_CONTROLS_VERSION,
            )
            meta_metrics["research_audit"] = audit_record
            metrics_path.write_text(
                json.dumps(meta_metrics, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False),
                encoding="utf-8",
            )

            outputs = (
                ("xauusd_m1_real_events", real_path),
                ("xauusd_m1_walkforward", walkforward_path),
                ("xauusd_m1_oos_calibration", calibration_path),
                ("xauusd_m1_meta_evaluation", metrics_path),
            )
            for kind, path in outputs:
                content = path.read_bytes()
                yield PipelineArtifact(
                    artifact_id=hashlib.sha256(content).hexdigest(),
                    kind=kind,
                    content=content,
                )


__all__ = ["FrozenXauusdM1Pipeline", "RawDatasetResolver"]
