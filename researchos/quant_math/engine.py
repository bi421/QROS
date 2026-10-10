from __future__ import annotations

import json
from collections.abc import Sequence
from hashlib import sha256
from typing import Any

from researchos.quant_engine.mathematical_falsification import (
    AuditStatus,
    audit_beta_bernoulli,
    audit_monte_carlo_replay,
)
from researchos.quant_engine.descriptive_statistics_audit import audit_descriptive_statistics
from researchos.quant_math.bayesian import beta_bernoulli
from researchos.quant_math.contracts import QuantMathResult
from researchos.quant_math.geometry import measure_market_geometry
from researchos.quant_math.monte_carlo import simulate_terminal_distribution
from researchos.quant_math.statistics import describe

QUANT_MATH_VERSION = "QUANT_MATH_V1"
AUDIT_INTEGRATION_VERSION = "QUANT_MATH_AUDIT_V1"


class QuantMathEngine:
    calculation_version = QUANT_MATH_VERSION
    audit_integration_version = AUDIT_INTEGRATION_VERSION

    def evaluate(
        self,
        prices: Sequence[float],
        successes: int | None = None,
        failures: int | None = None,
        monte_carlo_simulations: int | None = None,
        seed: int = 42,
    ) -> QuantMathResult:
        geometry = measure_market_geometry(prices)
        statistics = describe(prices)
        bayesian = None
        monte_carlo = None
        if successes is not None or failures is not None:
            if successes is None or failures is None:
                raise ValueError("successes and failures must be supplied together")
            bayesian = beta_bernoulli(successes, failures)
        if monte_carlo_simulations is not None:
            monte_carlo = simulate_terminal_distribution(
                prices, monte_carlo_simulations, seed
            )
        payload = {
            "calculation_version": self.calculation_version,
            "geometry": geometry.__dict__,
            "statistics": statistics.__dict__,
            "bayesian": None if bayesian is None else bayesian.__dict__,
            "monte_carlo": None if monte_carlo is None else monte_carlo.__dict__,
        }
        digest = sha256(
            json.dumps(
                payload, sort_keys=True, separators=(",", ":"), default=str
            ).encode()
        ).hexdigest()
        return QuantMathResult(
            self.calculation_version,
            geometry,
            statistics,
            bayesian,
            monte_carlo,
            digest,
        )

    def evaluate_with_audit(
        self,
        prices: Sequence[float],
        successes: int | None = None,
        failures: int | None = None,
        monte_carlo_simulations: int | None = None,
        seed: int = 42,
    ) -> dict[str, Any]:
        """Evaluate existing quant models and attach independent audit evidence.

        This verifies selected arithmetic/replay contracts only. It does not
        certify market-model assumptions, strategy profitability, or SaaS
        production readiness. Unsupported model claims remain inconclusive.
        """
        result = self.evaluate(
            prices=prices,
            successes=successes,
            failures=failures,
            monte_carlo_simulations=monte_carlo_simulations,
            seed=seed,
        )
        audits = [
            audit_descriptive_statistics(prices, result.statistics.__dict__).to_dict()
        ]
        if result.bayesian is not None:
            audits.append(audit_beta_bernoulli(result.bayesian.__dict__).to_dict())
        if result.monte_carlo is not None:
            audits.append(
                audit_monte_carlo_replay(
                    prices, result.monte_carlo.__dict__
                ).to_dict()
            )

        statuses = [AuditStatus(item["status"]) for item in audits]
        if AuditStatus.FALSIFIED in statuses:
            overall = AuditStatus.FALSIFIED
        elif AuditStatus.INVALID_INPUT in statuses:
            overall = AuditStatus.INVALID_INPUT
        elif not statuses or AuditStatus.INCONCLUSIVE in statuses:
            overall = AuditStatus.INCONCLUSIVE
        else:
            overall = AuditStatus.VERIFIED

        return {
            "audit_integration_version": self.audit_integration_version,
            "calculation_version": result.calculation_version,
            "result_hash": result.result_hash,
            "result": result.to_dict(),
            "mathematical_audits": audits,
            "overall_audit_status": overall.value,
            "profitability_verdict": "NOT_ASSESSED_BY_MATHEMATICAL_AUDIT",
            "limitations": [
                "VERIFIED means checked arithmetic or replay is reproducible, not that market assumptions are true.",
                "Monte Carlo replay uses the declared historical-return resampling algorithm and does not validate its iid assumption.",
                "Market geometry, model calibration, data leakage, transaction costs, and out-of-sample profitability are not yet independently audited by this integration.",
                "No profitability conclusion is inferred from missing or inconclusive evidence.",
            ],
        }
