from __future__ import annotations

from researchos.quant_engine.profitability_falsification import (
    ProfitabilityVerdict,
    assess_profitability,
)


def test_positive_after_costs_and_above_benchmark_can_pass_in_sample() -> None:
    net = [0.01 + (i % 3) * 0.0001 for i in range(300)]
    benchmark = [0.001 for _ in net]

    result = assess_profitability(
        net, benchmark, costs_included=True, block_length=5, seed=11
    )

    assert result.verdict is ProfitabilityVerdict.SUPPORTED_IN_SAMPLE
    assert result.net_return_ci is not None
    assert result.net_return_ci.lower > 0
    assert result.excess_return_ci is not None
    assert result.excess_return_ci.lower > 0
    assert result.supports_profitability_claim


def test_negative_net_edge_is_falsified_when_upper_bound_is_below_zero() -> None:
    net = [-0.001 for _ in range(100)]
    benchmark = [0.0 for _ in net]

    result = assess_profitability(
        net, benchmark, costs_included=True, maximum_drawdown=0.99,
        block_length=5, seed=12,
    )

    assert result.verdict is ProfitabilityVerdict.NOT_PROFITABLE
    assert result.net_return_ci is not None
    assert result.net_return_ci.upper < 0
    assert not result.supports_profitability_claim


def test_positive_return_but_no_benchmark_edge_is_rejected() -> None:
    net = [0.001 for _ in range(150)]
    benchmark = [0.002 for _ in net]

    result = assess_profitability(
        net, benchmark, costs_included=True, block_length=5, seed=13
    )

    assert result.verdict is ProfitabilityVerdict.NO_BENCHMARK_EDGE
    assert result.excess_return_ci is not None
    assert result.excess_return_ci.upper < 0


def test_missing_cost_declaration_fails_closed() -> None:
    result = assess_profitability(
        [0.01] * 100, [0.0] * 100, costs_included=False
    )

    assert result.verdict is ProfitabilityVerdict.INVALID_EVIDENCE
    assert any("costs" in reason for reason in result.reasons)


def test_misaligned_benchmark_fails_closed() -> None:
    result = assess_profitability(
        [0.01] * 100, [0.0] * 99, costs_included=True
    )

    assert result.verdict is ProfitabilityVerdict.INVALID_EVIDENCE
    assert any("equal length" in reason for reason in result.reasons)


def test_zero_centered_returns_remain_inconclusive() -> None:
    net = [0.001 if i % 2 == 0 else -0.001 for i in range(200)]
    benchmark = [0.0 for _ in net]

    result = assess_profitability(
        net, benchmark, costs_included=True, block_length=1, seed=14
    )

    assert result.verdict is ProfitabilityVerdict.INCONCLUSIVE
    assert not result.supports_profitability_claim


def test_drawdown_limit_can_reject_apparent_profitability() -> None:
    net = [0.02, -0.15, 0.03, -0.20] * 40
    benchmark = [0.0 for _ in net]

    result = assess_profitability(
        net, benchmark, costs_included=True, maximum_drawdown=0.10,
        block_length=5, seed=15,
    )

    assert result.verdict is ProfitabilityVerdict.RISK_LIMIT_BREACH
    assert result.max_drawdown is not None
    assert result.max_drawdown > 0.10
