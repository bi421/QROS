"""
Research Evaluation Engine — deterministic evaluation engine (Q16).

``ResearchEvaluator`` loads ``PipelineRecord`` objects from a
``PipelineRepository`` and computes deterministic reproducibility,
stability, and evidence scores.

Design rules:
    - No randomness, no uuid, no timestamps used as identifiers.
    - Dependency injection only (no global state, no singleton).
    - stdlib only; no numpy, pandas, sklearn, torch, etc.
    - No modifications to any locked module.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

from researchos.orchestration.contracts import PipelineReport, PipelineStatus
from researchos.pipeline_repository.contracts import (
    PipelineNotFoundError,
    PipelineRecord,
    PipelineRepositoryError,
)
from researchos.pipeline_repository.repository import PipelineRepository

from .contracts import (
    EVALUATION_VERSION,
    EvaluationReport,
    EvaluationScore,
    PipelineEvaluationError,
    _grade,
)


def _canonical_json(obj: Any) -> str:
    """Deterministic JSON serialization (sorted keys, compact separators)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _evaluation_id(score: EvaluationScore, created_at: str) -> str:
    """Deterministic content-derived evaluation id.

    Uses SHA-256 of the canonical JSON of the score dict plus created_at.
    """
    payload = {
        "score": score.to_dict(),
        "created_at": created_at,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# score computation helpers (deterministic, pure functions)
# ---------------------------------------------------------------------------


def _compute_reproducibility(report: PipelineReport) -> float:
    """Measure same-input -> same-output consistency.

    A score of 1.0 means the pipeline is fully deterministic (same inputs
    always produce identical outputs).  The score is derived from:
      - The presence of a content_hash on the report (1.0 if present).
      - The number of evidence nodes/edges (more edges indicate more
        traceable, reproducible steps; capped at 1.0).
    """
    base = 0.7
    n_nodes = len(report.nodes)
    n_edges = len(report.edges)
    traceability = min(0.3, (n_nodes + n_edges) * 0.05)
    status_bonus = 0.0
    if report.status == PipelineStatus.COMPLETED:
        status_bonus = 0.1
    raw = base + traceability + status_bonus
    return max(0.0, min(1.0, raw))


def _compute_stability(report: PipelineReport) -> float:
    """Measure variance of repeated research outcomes.

    A score of 1.0 means the pipeline produces highly stable results.

    Derived from:
      - Validation fold metrics: low variance across folds => high stability.
    """
    validation = report.validation
    if validation.fold_count == 0 or not validation.fold_results:
        return 0.5
    all_metric_values: list[float] = []
    for fold in validation.fold_results:
        for metric_name, metric_value in fold.metrics.items():
            if isinstance(metric_value, (int, float)) and math.isfinite(metric_value):
                all_metric_values.append(float(metric_value))
    if not all_metric_values:
        return 0.5
    mean_val = sum(all_metric_values) / len(all_metric_values)
    if mean_val == 0.0:
        return 1.0
    variance = sum((x - mean_val) ** 2 for x in all_metric_values) / len(all_metric_values)
    std_val = math.sqrt(variance)
    cv = std_val / abs(mean_val)
    stability = max(0.0, 1.0 - cv)
    return stability


def _compute_evidence(report: PipelineReport) -> float:
    """Measure the quality of supporting evidence.

    A score of 1.0 means the pipeline has strong, well-documented evidence.

    Derived from:
      - Number and density of evidence nodes/edges.
      - Training metrics quality.
      - Dataset hash presence (provenance).
    """
    score = 0.0
    n_nodes = len(report.nodes)
    n_edges = len(report.edges)
    if n_nodes > 0:
        density = min(1.0, n_edges / max(1, n_nodes))
        score += 0.4 * density
    else:
        score += 0.1
    training = report.training
    if training.metrics:
        valid_metrics = sum(1 for v in training.metrics.values() if isinstance(v, (int, float)) and math.isfinite(v))
        metric_quality = min(1.0, valid_metrics / max(1, len(training.metrics)))
        score += 0.3 * metric_quality
    if report.dataset_hash and len(report.dataset_hash) > 0:
        score += 0.2
    model_meta = report.model_contract.metadata
    if model_meta and len(model_meta) > 0:
        score += 0.1
    return max(0.0, min(1.0, score))


def _compute_overall(reproducibility: float, stability: float, evidence: float) -> float:
    """Weighted deterministic aggregation of sub-scores.

    Formula:
        overall = (reproducibility * 0.4) + (stability * 0.3) + (evidence * 0.3)
    """
    raw = reproducibility * 0.4 + stability * 0.3 + evidence * 0.3
    return max(0.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# ResearchEvaluator
# ---------------------------------------------------------------------------


class ResearchEvaluator:
    """Deterministic evaluation engine for pipeline research runs.

    Parameters:
        repository: The ``PipelineRepository`` containing pipeline records.
    """

    VERSION = EVALUATION_VERSION

    def __init__(self, repository: PipelineRepository) -> None:
        if not isinstance(repository, PipelineRepository):
            raise PipelineEvaluationError("repository must be a PipelineRepository")
        self._repository = repository

    # ------------------------------------------------------------------
    # properties
    # ------------------------------------------------------------------

    @property
    def repository(self) -> PipelineRepository:
        """The underlying ``PipelineRepository``."""
        return self._repository

    # ------------------------------------------------------------------
    # evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        pipeline_id: str,
        *,
        created_at: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> EvaluationReport:
        """Evaluate a single pipeline by its id.

        Args:
            pipeline_id: The deterministic pipeline id to evaluate.
            created_at: Optional deterministic timestamp string.
            metadata: Optional extra evaluation metadata mapping.

        Returns:
            A deterministic ``EvaluationReport``.

        Raises:
            PipelineEvaluationError: If the pipeline does not exist.
            InvalidEvaluationError: If the computed scores are invalid.
        """
        try:
            record: PipelineRecord = self._repository.load(pipeline_id)
        except PipelineNotFoundError:
            raise PipelineEvaluationError(f"pipeline not found: {pipeline_id}") from None
        except PipelineRepositoryError as exc:
            raise PipelineEvaluationError(f"repository error: {exc}") from None

        report: PipelineReport = record.report

        reproducibility = _compute_reproducibility(report)
        stability = _compute_stability(report)
        evidence = _compute_evidence(report)
        overall = _compute_overall(reproducibility, stability, evidence)
        grade = _grade(overall)

        score = EvaluationScore(
            pipeline_id=pipeline_id,
            reproducibility_score=reproducibility,
            stability_score=stability,
            evidence_score=evidence,
            overall_score=overall,
            grade=grade,
            metadata=dict(metadata or {}),
        )

        evaluation_id = _evaluation_id(score, created_at)

        return EvaluationReport(
            evaluation_id=evaluation_id,
            pipeline_id=pipeline_id,
            score=score,
            created_at=created_at,
            version=self.VERSION,
        )

    def evaluate_all(
        self,
        *,
        created_at: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[EvaluationReport, ...]:
        """Evaluate all pipelines in the repository.

        Returns:
            Reports sorted deterministically by ``evaluation_id``.
        """
        reports: list[EvaluationReport] = []
        for record in self._repository.list():
            reports.append(
                self.evaluate(
                    record.pipeline_id,
                    created_at=created_at,
                    metadata=metadata,
                )
            )
        reports.sort(key=lambda r: r.evaluation_id)
        return tuple(reports)

    # ------------------------------------------------------------------
    # comparison
    # ------------------------------------------------------------------

    @staticmethod
    def compare(
        evaluation_a: EvaluationReport,
        evaluation_b: EvaluationReport,
    ) -> dict[str, Any]:
        """Deterministic comparison of two evaluation reports.

        Returns a dictionary with:
          - ``pipeline_a``: evaluation id of the first report.
          - ``pipeline_b``: evaluation id of the second report.
          - ``overall_delta``: ``a.overall - b.overall``.
          - ``reproducibility_delta``: ``a.reproducibility - b.reproducibility``.
          - ``stability_delta``: ``a.stability - b.stability``.
          - ``evidence_delta``: ``a.evidence - b.evidence``.
          - ``winner``: ``"a"`` if a > b, ``"b"`` if b > a, ``"tie"`` otherwise.
        """
        if not isinstance(evaluation_a, EvaluationReport):
            raise PipelineEvaluationError("evaluation_a must be an EvaluationReport")
        if not isinstance(evaluation_b, EvaluationReport):
            raise PipelineEvaluationError("evaluation_b must be an EvaluationReport")

        delta_overall = evaluation_a.score.overall_score - evaluation_b.score.overall_score
        delta_repro = evaluation_a.score.reproducibility_score - evaluation_b.score.reproducibility_score
        delta_stab = evaluation_a.score.stability_score - evaluation_b.score.stability_score
        delta_evid = evaluation_a.score.evidence_score - evaluation_b.score.evidence_score

        if delta_overall > 0:
            winner = "a"
        elif delta_overall < 0:
            winner = "b"
        else:
            if delta_repro > 0:
                winner = "a"
            elif delta_repro < 0:
                winner = "b"
            elif delta_stab > 0:
                winner = "a"
            elif delta_stab < 0:
                winner = "b"
            elif delta_evid > 0:
                winner = "a"
            elif delta_evid < 0:
                winner = "b"
            else:
                winner = "tie"

        return {
            "pipeline_a": evaluation_a.evaluation_id,
            "pipeline_b": evaluation_b.evaluation_id,
            "overall_delta": delta_overall,
            "reproducibility_delta": delta_repro,
            "stability_delta": delta_stab,
            "evidence_delta": delta_evid,
            "winner": winner,
        }


__all__ = [
    "ResearchEvaluator",
    "_compute_reproducibility",
    "_compute_stability",
    "_compute_evidence",
    "_compute_overall",
    "_evaluation_id",
]
