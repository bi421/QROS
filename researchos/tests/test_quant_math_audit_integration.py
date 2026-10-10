from researchos.quant_engine.descriptive_statistics_audit import (
    audit_descriptive_statistics,
)
from researchos.quant_engine.mathematical_falsification import AuditStatus
from researchos.quant_math.engine import QuantMathEngine


def test_engine_attaches_independent_statistics_bayesian_and_monte_carlo_audits() -> None:
    report = QuantMathEngine().evaluate_with_audit(
        prices=[100.0, 101.0, 99.5, 102.0, 101.0, 103.5],
        successes=7,
        failures=3,
        monte_carlo_simulations=250,
        seed=19,
    )

    assert report["audit_integration_version"] == "QUANT_MATH_AUDIT_V1"
    assert report["result_hash"] == report["result"]["result_hash"]
    assert {item["model"] for item in report["mathematical_audits"]} == {
        "descriptive_statistics",
        "beta_bernoulli",
        "monte_carlo_replay",
    }
    assert all(
        item["status"] == AuditStatus.VERIFIED.value
        for item in report["mathematical_audits"]
    )
    assert report["overall_audit_status"] == AuditStatus.VERIFIED.value
    assert (
        report["profitability_verdict"]
        == "NOT_ASSESSED_BY_MATHEMATICAL_AUDIT"
    )


def test_statistics_audit_falsifies_tampered_reported_mean() -> None:
    prices = [100.0, 101.0, 99.5, 102.0]
    measurement = QuantMathEngine().evaluate(prices=prices).statistics.__dict__.copy()
    measurement["mean"] += 1.0

    audit = audit_descriptive_statistics(prices, measurement)

    assert audit.status is AuditStatus.FALSIFIED
    assert audit.checked_claim == "mean"


def test_engine_audits_statistics_without_optional_models() -> None:
    report = QuantMathEngine().evaluate_with_audit(
        prices=[100.0, 101.0, 99.5, 102.0]
    )

    assert [item["model"] for item in report["mathematical_audits"]] == [
        "descriptive_statistics"
    ]
    assert report["overall_audit_status"] == AuditStatus.VERIFIED.value
    assert (
        report["profitability_verdict"]
        == "NOT_ASSESSED_BY_MATHEMATICAL_AUDIT"
    )


def test_existing_evaluate_contract_remains_unchanged() -> None:
    result = QuantMathEngine().evaluate(
        prices=[100.0, 101.0, 99.5, 102.0],
        successes=2,
        failures=1,
        monte_carlo_simulations=50,
        seed=7,
    )

    assert result.calculation_version == "QUANT_MATH_V1"
    assert result.bayesian is not None
    assert result.monte_carlo is not None
    assert len(result.result_hash) == 64
