from researchos.quant_engine.mathematical_falsification import AuditStatus
from researchos.quant_math.engine import QuantMathEngine


def test_engine_attaches_independent_bayesian_and_monte_carlo_audits() -> None:
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


def test_engine_does_not_claim_audit_pass_when_no_supported_model_was_checked() -> None:
    report = QuantMathEngine().evaluate_with_audit(
        prices=[100.0, 101.0, 99.5, 102.0]
    )

    assert report["mathematical_audits"] == []
    assert report["overall_audit_status"] == AuditStatus.INCONCLUSIVE.value
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
