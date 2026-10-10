from researchos.quant_engine.mathematical_falsification import (
    AuditStatus,
    audit_beta_bernoulli,
    audit_monte_carlo_summary,
    audit_monte_carlo_replay,
)


def test_beta_bernoulli_identity_is_verified() -> None:
    result = audit_beta_bernoulli({
        "prior_alpha": 1.0,
        "prior_beta": 1.0,
        "successes": 7,
        "failures": 3,
        "posterior_alpha": 8.0,
        "posterior_beta": 4.0,
        "posterior_mean": 8.0 / 12.0,
    })
    assert result.status is AuditStatus.VERIFIED
    assert result.absolute_error == 0.0


def test_beta_bernoulli_wrong_posterior_is_falsified() -> None:
    result = audit_beta_bernoulli({
        "prior_alpha": 1.0,
        "prior_beta": 1.0,
        "successes": 7,
        "failures": 3,
        "posterior_alpha": 8.0,
        "posterior_beta": 4.0,
        "posterior_mean": 0.9,
    })
    assert result.status is AuditStatus.FALSIFIED
    assert result.checked_claim == "posterior_mean"
    assert result.expected == 8.0 / 12.0


def test_beta_bernoulli_invalid_prior_fails_closed() -> None:
    result = audit_beta_bernoulli({
        "prior_alpha": 0.0,
        "prior_beta": 1.0,
        "successes": 7,
        "failures": 3,
        "posterior_alpha": 7.0,
        "posterior_beta": 4.0,
        "posterior_mean": 7.0 / 11.0,
    })
    assert result.status is AuditStatus.INVALID_INPUT


def test_monte_carlo_summary_does_not_claim_proof_from_aggregates() -> None:
    result = audit_monte_carlo_summary({
        "simulations": 1000,
        "mean_terminal": 101.0,
        "standard_deviation_terminal": 5.0,
        "percentile_05": 92.0,
        "percentile_50": 100.0,
        "percentile_95": 110.0,
    })
    assert result.status is AuditStatus.INCONCLUSIVE


def test_monte_carlo_invalid_percentile_order_fails_closed() -> None:
    result = audit_monte_carlo_summary({
        "simulations": 1000,
        "mean_terminal": 101.0,
        "standard_deviation_terminal": 5.0,
        "percentile_05": 105.0,
        "percentile_50": 100.0,
        "percentile_95": 110.0,
    })
    assert result.status is AuditStatus.INVALID_INPUT


def test_monte_carlo_replay_verifies_existing_engine_output() -> None:
    from researchos.quant_math.monte_carlo import simulate_terminal_distribution

    prices = [100.0, 101.0, 99.5, 102.0, 101.0, 103.5]
    measurement = simulate_terminal_distribution(prices, simulations=250, seed=19)
    result = audit_monte_carlo_replay(prices, measurement.__dict__)
    assert result.status is AuditStatus.VERIFIED


def test_monte_carlo_replay_falsifies_tampered_output() -> None:
    from researchos.quant_math.monte_carlo import simulate_terminal_distribution

    prices = [100.0, 101.0, 99.5, 102.0, 101.0, 103.5]
    measurement = simulate_terminal_distribution(prices, simulations=250, seed=19)
    reported = dict(measurement.__dict__)
    reported["mean_terminal"] += 1.0
    result = audit_monte_carlo_replay(prices, reported)
    assert result.status is AuditStatus.FALSIFIED
    assert result.checked_claim == "mean_terminal"
