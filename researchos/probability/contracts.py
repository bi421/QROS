"""Contracts for versioned probability and trading-edge analyses."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProbabilityMethod(str, Enum):
    """Declared method families; analysis code must identify its method explicitly."""

    DESCRIPTIVE = "descriptive"
    EXPECTED_VALUE = "expected_value"
    CONDITIONAL_PROBABILITY = "conditional_probability"
    BAYES = "bayes"
    BINOMIAL = "binomial"
    BOOTSTRAP = "bootstrap"
    BLOCK_BOOTSTRAP = "block_bootstrap"
    GARCH = "garch"
    VAR = "var"
    EXPECTED_SHORTFALL = "expected_shortfall"
    GBM = "gbm"
    ORNSTEIN_UHLENBECK = "ornstein_uhlenbeck"
    STUDENT_T = "student_t"
    EVT = "evt"
    COPULA = "copula"
    SHANNON_ENTROPY = "shannon_entropy"
    MUTUAL_INFORMATION = "mutual_information"
    SHARPE_INFERENCE = "sharpe_inference"
    PSR = "probabilistic_sharpe_ratio"
    DSR = "deflated_sharpe_ratio"
    PBO = "probability_backtest_overfitting"
    CPCV = "combinatorial_purged_cross_validation"
    REALITY_CHECK = "white_reality_check"
    SPA = "hansen_spa"
    CALIBRATION = "probability_calibration"


@dataclass(frozen=True)
class ProbabilityAnalysis:
    """Immutable manifest for a probability-producing research artifact.

    The contract deliberately stores the meaning and provenance of a probability,
    rather than collapsing every method into a single confidence score.
    """

    analysis_id: str
    claim_id: str
    method: ProbabilityMethod | str
    population_definition: str
    time_window: str
    data_version: str
    data_hash: str
    model_version: str = ""
    assumptions: tuple[str, ...] = ()
    sample_size: int | None = None
    effective_sample_size: float | None = None
    point_estimate: float | None = None
    uncertainty_interval: tuple[float, float] | None = None
    probability_definition: str = ""
    effect_size: float | None = None
    multiple_testing_context: str = ""
    selection_count: int | None = None
    integrity_gate_status: str = "UNKNOWN"
    out_of_sample_status: str = "UNKNOWN"
    replication_status: str = "UNKNOWN"
    calibration_status: str = "NOT_APPLICABLE"
    economic_cost_model: str = ""
    result_artifact_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "method", ProbabilityMethod(self.method))
        allowed_statuses = {
            "integrity_gate_status": {"UNKNOWN", "PASS", "PASSED", "FAIL", "FAILED"},
            "out_of_sample_status": {
                "UNKNOWN", "PASS", "PASSED", "FAIL", "FAILED", "NOT_APPLICABLE"
            },
            "replication_status": {
                "UNKNOWN", "PASS", "PASSED", "FAIL", "FAILED", "NOT_APPLICABLE"
            },
            "calibration_status": {
                "UNKNOWN", "PASS", "PASSED", "FAIL", "FAILED", "NOT_APPLICABLE",
                "INSUFFICIENT_SAMPLE"
            },
        }
        for name, values in allowed_statuses.items():
            value = getattr(self, name)
            if value not in values:
                raise ValueError(f"{name} has unsupported status: {value}")
        if self.selection_count is not None and self.selection_count < 1:
            raise ValueError("selection_count must be >= 1 when provided")
        if self.selection_count is None and self.multiple_testing_context.strip():
            raise ValueError("selection_count is required when multiple_testing_context is declared")
        if not self.analysis_id.strip():
            raise ValueError("analysis_id is required")
        if not self.claim_id.strip():
            raise ValueError("claim_id is required")
        if not self.population_definition.strip():
            raise ValueError("population_definition is required")
        if not self.time_window.strip():
            raise ValueError("time_window is required")
        if not self.data_version.strip():
            raise ValueError("data_version is required")
        if not self.data_hash.strip():
            raise ValueError("data_hash is required")
        if self.sample_size is not None and self.sample_size < 0:
            raise ValueError("sample_size must be >= 0")
        if self.effective_sample_size is not None and self.effective_sample_size <= 0:
            raise ValueError("effective_sample_size must be > 0")
        if self.uncertainty_interval is not None:
            lo, hi = self.uncertainty_interval
            if lo > hi:
                raise ValueError("uncertainty_interval lower bound must be <= upper bound")

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "claim_id": self.claim_id,
            "method": self.method.value,
            "population_definition": self.population_definition,
            "time_window": self.time_window,
            "data_version": self.data_version,
            "data_hash": self.data_hash,
            "model_version": self.model_version,
            "assumptions": list(self.assumptions),
            "sample_size": self.sample_size,
            "effective_sample_size": self.effective_sample_size,
            "point_estimate": self.point_estimate,
            "uncertainty_interval": list(self.uncertainty_interval) if self.uncertainty_interval else None,
            "probability_definition": self.probability_definition,
            "effect_size": self.effect_size,
            "multiple_testing_context": self.multiple_testing_context,
            "selection_count": self.selection_count,
            "integrity_gate_status": self.integrity_gate_status,
            "out_of_sample_status": self.out_of_sample_status,
            "replication_status": self.replication_status,
            "calibration_status": self.calibration_status,
            "economic_cost_model": self.economic_cost_model,
            "result_artifact_hash": self.result_artifact_hash,
            "metadata": dict(self.metadata),
        }
