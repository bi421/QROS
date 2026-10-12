from __future__ import annotations

import pytest

pytest.importorskip("cpp_quant_engine.qros_biberion")
from cpp_quant_engine import qros_biberion as biberion


def test_volume_surge_uses_only_prior_window() -> None:
    detector = biberion.VolumeSurge(3, 1.0)
    assert detector.observe(10.0) is False
    assert detector.observe(10.0) is False
    assert detector.observe(10.0) is False
    assert detector.observe(100.0) is True
    assert detector.threshold == pytest.approx(10.0)


def test_lockdown_blocks_cross() -> None:
    closes = [float(x) for x in range(1, 31)]
    result = biberion.evaluate_cross(closes, [100.0, 101.0], 5, 25, True, True)
    assert result.approved is False
    assert result.reason == "sideline_lockdown"


def test_cash_basket_rejects_overallocation() -> None:
    limits = biberion.BasketLimits()
    limits.equity = 100_000.0
    limits.max_basket_fraction = 0.10
    limits.max_asset_fraction = 0.01
    limits.max_asset_risk_fraction = 0.001
    limits.max_basket_risk_fraction = 0.005
    proposal = biberion.BasketProposal()
    proposal.symbol = "A"
    proposal.entry = 100.0
    proposal.stop = 99.0
    proposal.requested_notional = 2_000.0
    decision = biberion.approve_cash_basket(limits, [proposal])
    assert decision.approved is False
    assert decision.reason == "asset_allocation_or_stop_risk_exceeded"
