"""
Live Experiment Certification Engine.
Bridges cpp_quant_engine WFO results into the EvidenceRegistry with strict determinism.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List
from researchos.core.identity import deterministic_hash
from researchos.objects.evidence import Evidence, EvidenceRegistry
from researchos.experiments.runtime_certifier import RuntimeCertifier


@dataclass(frozen=True)
class DatasetFingerprint:
    """Immutable dataset identity."""
    asset: str
    timeframe: str
    start_date: str
    end_date: str
    content_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "timeframe": self.timeframe,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class StrategyFingerprint:
    """Immutable strategy identity."""
    name: str
    parameters: Dict[str, Any]
    features: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "parameters": self.parameters,
            "features": sorted(self.features),
        }


@dataclass(frozen=True)
class OOSMetrics:
    """Out-of-sample performance metrics."""
    total_trades: int
    win_rate: float
    profit_factor: float
    sharpe_ratio: float
    max_drawdown: float
    net_pnl: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "net_pnl": self.net_pnl,
        }


class LiveCertifier:
    """Certifies live backtest results."""

    def __init__(self, registry: EvidenceRegistry):
        self.certifier = RuntimeCertifier(registry)
        self.registry = registry

    def certify_wfo_result(
        self,
        dataset: DatasetFingerprint,
        strategy: StrategyFingerprint,
        oos_metrics: OOSMetrics,
        hypothesis_id: str,
        interpretation: str,
    ) -> Evidence:
        experiment_payload = {
            "dataset": dataset.to_dict(),
            "strategy": strategy.to_dict(),
        }
        experiment_id = deterministic_hash(experiment_payload)

        run_payload = {
            "experiment_id": experiment_id,
            "oos_metrics": oos_metrics.to_dict(),
        }
        run_id = deterministic_hash(run_payload)

        if (
            oos_metrics.sharpe_ratio > 1.0
            and oos_metrics.profit_factor > 1.5
            and oos_metrics.win_rate > 0.55
        ):
            direction = "Supporting"
        elif oos_metrics.max_drawdown < -0.20:
            direction = "Contradicting"
        else:
            direction = "Neutral"

        evidence = self.certifier.certify_run(
            experiment_id=experiment_id,
            run_id=run_id,
            result_data=oos_metrics.to_dict(),
            hypothesis_id=hypothesis_id,
            interpretation=interpretation,
            direction=direction,
        )

        return evidence

    def generate_report(self, evidence: Evidence) -> str:
        report = f"""
================================================================================
                    RESEARCHOS CERTIFIED EVIDENCE REPORT
================================================================================

Evidence ID: {evidence.id}
Observation ID: {evidence.observation_id}
Hypothesis ID: {evidence.hypothesis_id}
Direction: {evidence.direction}
Quality: {evidence.quality:.4f}
Confidence: {evidence.confidence:.4f}

Interpretation:
{evidence.interpretation}

Certification Status: IMMUTABLE & APPEND-ONLY
Timestamp: {evidence.created_at.isoformat()}

================================================================================
"""
        return report
