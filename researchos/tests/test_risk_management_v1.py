from __future__ import annotations

import pytest

from researchos.risk import (
    ExecutionMode,
    RiskAccountSnapshot,
    RiskAuditEvent,
    RiskOrderIntent,
    RiskPolicy,
    RiskGateResult,
    StrategyState,
    evaluate_risk_gate,
    validate_strategy_transition,
)
from researchos.risk.contracts import RISK_AUDIT_SCHEMA_VERSION


POLICY = RiskPolicy()


def _account(
    *,
    equity: float = 10_000.0,
    day_start_equity: float = 10_000.0,
    high_water_mark: float = 10_000.0,
    strategy_loss_amount: float = 0.0,
    open_risk_amount: float = 0.0,
    gross_exposure_amount: float = 0.0,
    instrument_exposure_amount: float = 0.0,
    realized_pnl: float = 0.0,
    unrealized_pnl: float = 0.0,
    trading_costs: float = 0.0,
    available_margin: float | None = 10_000.0,
    kill_switch_active: bool = False,
) -> RiskAccountSnapshot:
    return RiskAccountSnapshot(
        equity=equity,
        day_start_equity=day_start_equity,
        high_water_mark=high_water_mark,
        strategy_reference_equity=10_000.0,
        strategy_loss_amount=strategy_loss_amount,
        open_risk_amount=open_risk_amount,
        gross_exposure_amount=gross_exposure_amount,
        instrument_exposure_amount=instrument_exposure_amount,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        trading_costs=trading_costs,
        available_margin=available_margin,
        kill_switch_active=kill_switch_active,
    )


def _intent(**overrides: object) -> RiskOrderIntent:
    values: dict[str, object] = {
        "asset": "XAUUSD",
        "strategy_id": "strategy-001",
        "requested_position_size": 1.0,
        "position_notional": 1_000.0,
        "risk_amount": 25.0,
        "execution_mode": ExecutionMode.RESEARCH,
        "strategy_state": StrategyState.RESEARCH,
        "research_id": "research-001",
        "probability_calibration_status": "Well-Calibrated",
    }
    values.update(overrides)
    return RiskOrderIntent(**values)  # type: ignore[arg-type]


def test_flat_research_gate_passes_without_execution_authorization() -> None:
    gate = evaluate_risk_gate(_account(), _intent(), policy=POLICY)

    assert gate.status == "RESEARCH_ONLY"
    assert gate.execution_allowed is False
    assert gate.hard_failures == ()


@pytest.mark.parametrize(
    ("kwargs", "failure"),
    [
        (
            {
                "equity": 7_999.0,
                "day_start_equity": 10_000.0,
                "realized_pnl": -2_001.0,
            },
            "MAX_DAILY_LOSS_BREACHED",
        ),
        (
            {
                "equity": 9_399.0,
                "high_water_mark": 10_000.0,
                "realized_pnl": -601.0,
            },
            "MAX_TOTAL_DRAWDOWN_BREACHED",
        ),
        (
            {
                "strategy_loss_amount": 301.0,
                "realized_pnl": -301.0,
            },
            "MAX_STRATEGY_LOSS_BREACHED",
        ),
    ],
)
def test_account_loss_limits_block(
    kwargs: dict[str, object],
    failure: str,
) -> None:
    gate = evaluate_risk_gate(_account(**kwargs), _intent(), policy=POLICY)
    assert gate.status == "BLOCKED"
    assert failure in gate.hard_failures


def test_per_trade_risk_limit_blocks_without_auto_reduction() -> None:
    gate = evaluate_risk_gate(
        _account(),
        _intent(risk_amount=51.0),
        policy=POLICY,
    )
    assert "MAX_LOSS_PER_TRADE_BREACHED" in gate.hard_failures
    assert gate.execution_allowed is False


def test_portfolio_open_risk_limit_blocks() -> None:
    gate = evaluate_risk_gate(
        _account(open_risk_amount=80.0),
        _intent(risk_amount=25.0),
        policy=POLICY,
    )
    assert "MAX_PORTFOLIO_OPEN_RISK_BREACHED" in gate.hard_failures


def test_gross_and_single_instrument_exposure_limits_block() -> None:
    gate = evaluate_risk_gate(
        _account(gross_exposure_amount=29_500.0, instrument_exposure_amount=14_500.0),
        _intent(position_notional=1_000.0),
        policy=POLICY,
    )
    assert "MAX_GROSS_EXPOSURE_BREACHED" in gate.hard_failures
    assert "MAX_SINGLE_INSTRUMENT_EXPOSURE_BREACHED" in gate.hard_failures


@pytest.mark.parametrize(
    ("override", "failure"),
    [
        ({"data_age_seconds": 6.0}, "STALE_MARKET_DATA"),
        ({"session_open": False}, "MARKET_SESSION_CLOSED"),
        ({"symbol_permitted": False}, "SYMBOL_NOT_PERMITTED"),
        ({"strategy_permitted": False}, "STRATEGY_NOT_PERMITTED"),
        ({"duplicate_order": True}, "DUPLICATE_ORDER"),
        ({"orders_last_minute": 10}, "ORDER_RATE_LIMIT_BREACHED"),
        ({"price_deviation_bps": 101.0}, "FAT_FINGER_PRICE_BAND_BREACHED"),
        ({"margin_required": 10001.0}, "INSUFFICIENT_AVAILABLE_MARGIN"),
    ],
)
def test_operational_pretrade_limits_block(
    override: dict[str, object],
    failure: str,
) -> None:
    gate = evaluate_risk_gate(_account(), _intent(**override), policy=POLICY)
    assert failure in gate.hard_failures


def test_kill_switch_blocks_everything() -> None:
    gate = evaluate_risk_gate(
        _account(kill_switch_active=True),
        _intent(),
        policy=POLICY,
    )
    assert gate.status == "BLOCKED"
    assert "KILL_SWITCH_ACTIVE" in gate.hard_failures


def test_paper_requires_calibration_and_eligible_state() -> None:
    gate = evaluate_risk_gate(
        _account(),
        _intent(
            execution_mode=ExecutionMode.PAPER,
            strategy_state=StrategyState.RESEARCH,
            probability_calibration_status=None,
        ),
        policy=POLICY,
    )
    assert "PROBABILITY_NOT_WELL_CALIBRATED" in gate.hard_failures
    assert "STRATEGY_NOT_PAPER_ELIGIBLE" in gate.hard_failures


def test_live_requires_deployment_eligibility_and_positive_notional() -> None:
    gate = evaluate_risk_gate(
        _account(),
        _intent(
            execution_mode=ExecutionMode.LIVE,
            strategy_state=StrategyState.DEPLOYMENT_ELIGIBLE,
            position_notional=0.0,
            probability_calibration_status="Well-Calibrated",
        ),
        policy=POLICY,
    )
    assert "MISSING_POSITION_NOTIONAL" in gate.hard_failures


def test_zero_risk_budget_blocks() -> None:
    gate = evaluate_risk_gate(
        _account(),
        _intent(risk_amount=0.0, requested_position_size=0.0),
        policy=POLICY,
    )
    assert "NO_POSITIVE_RISK_BUDGET" in gate.hard_failures


def test_equity_ledger_requires_reconciliation() -> None:
    with pytest.raises(ValueError, match="reconcile"):
        _account(equity=9_999.0)


def test_warning_is_emitted_before_hard_limit() -> None:
    gate = evaluate_risk_gate(
        _account(open_risk_amount=60.0),
        _intent(risk_amount=20.0),
        policy=POLICY,
    )
    assert gate.status == "RESEARCH_ONLY"
    assert "OPEN_RISK_UTILIZATION_HIGH" in gate.warnings


def test_risk_audit_event_is_content_addressed_and_immutable() -> None:
    gate = RiskGateResult(
        schema_version="risk.v2",
        status="BLOCKED",
        execution_allowed=False,
        hard_failures=("MAX_DAILY_LOSS_BREACHED",),
        warnings=(),
        policy_version=POLICY.version,
        research_id="research-001",
    )
    first = RiskAuditEvent.from_gate(
        gate,
        asset="XAUUSD",
        strategy_id="strategy-001",
        timestamp="2026-10-03T00:00:00Z",
    )
    second = RiskAuditEvent.from_gate(
        gate,
        asset="XAUUSD",
        strategy_id="strategy-001",
        timestamp="2026-10-03T00:00:00Z",
    )

    assert first == second
    assert first.event_id
    assert first.to_dict()["schema_version"] == RISK_AUDIT_SCHEMA_VERSION
    with pytest.raises(AttributeError):
        first.status = "PASS"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (StrategyState.RESEARCH, StrategyState.VALIDATED),
        (StrategyState.VALIDATED, StrategyState.RISK_REVIEW),
        (StrategyState.RISK_REVIEW, StrategyState.PAPER_ELIGIBLE),
        (StrategyState.PAPER_ELIGIBLE, StrategyState.DEPLOYMENT_ELIGIBLE),
        (StrategyState.DEPLOYMENT_ELIGIBLE, StrategyState.ACTIVE),
        (StrategyState.ACTIVE, StrategyState.SUSPENDED),
        (StrategyState.SUSPENDED, StrategyState.RISK_REVIEW),
    ],
)
def test_strategy_state_machine_allows_governed_transitions(
    current: StrategyState,
    target: StrategyState,
) -> None:
    validate_strategy_transition(current, target)


def test_strategy_state_machine_rejects_skipped_state() -> None:
    with pytest.raises(ValueError, match="invalid strategy transition"):
        validate_strategy_transition(
            StrategyState.RESEARCH,
            StrategyState.DEPLOYMENT_ELIGIBLE,
        )
