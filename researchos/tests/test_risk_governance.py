from __future__ import annotations

import json

import pytest

from researchos.risk import (
    RiskAccountState,
    RiskCalculation,
    RiskLimits,
    RiskViolationCode,
    StrategyRiskState,
    StrategyStateTransitionError,
    evaluate_pretrade_risk,
    validate_strategy_transition,
)


def _risk(
    *,
    account_equity: float = 10_000.0,
    final_risk_fraction: float = 0.0025,
) -> RiskCalculation:
    return RiskCalculation(
        schema_version="risk.v1",
        asset="XAUUSD",
        direction="bullish",
        probability=0.60,
        win_loss_ratio=1.5,
        full_kelly_fraction=0.3333333333333333,
        fractional_kelly_fraction=final_risk_fraction,
        final_risk_fraction=final_risk_fraction,
        risk_amount=account_equity * final_risk_fraction,
        position_size=None,
        capped=False,
        status="CALCULATED",
        research_id="research-001",
    )


def _account(**overrides: object) -> RiskAccountState:
    data: dict[str, object] = {
        "day_start_equity": 10_000.0,
        "current_equity": 10_000.0,
        "high_water_mark": 10_000.0,
        "strategy_reference_equity": 10_000.0,
        "strategy_pnl": 0.0,
        "open_risk_amount": 0.0,
        "gross_exposure": 0.0,
        "single_instrument_exposure": 0.0,
        "kill_switch_active": False,
        "kill_switch_reason": None,
    }
    data.update(overrides)
    return RiskAccountState(**data)


def _evaluate(
    *,
    risk: RiskCalculation | None = None,
    account: RiskAccountState | None = None,
    limits: RiskLimits | None = None,
    proposed_notional: float | None = 1_000.0,
    strategy_state: StrategyRiskState | str = StrategyRiskState.RISK_REVIEW,
    research_valid: bool = True,
):
    return evaluate_pretrade_risk(
        risk or _risk(),
        account=account or _account(),
        limits=limits or RiskLimits(),
        proposed_notional=proposed_notional,
        strategy_state=strategy_state,
        research_valid=research_valid,
    )


@pytest.mark.parametrize(
    "field",
    [
        "day_start_equity",
        "current_equity",
        "high_water_mark",
        "strategy_reference_equity",
    ],
)
def test_account_rejects_non_finite_equity(field: str) -> None:
    with pytest.raises(ValueError, match="finite"):
        _account(**{field: float("nan")}).validate()


def test_limits_reject_non_finite_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        RiskLimits(max_daily_loss_fraction=float("nan")).validate()
    with pytest.raises(ValueError, match="finite"):
        RiskLimits(max_gross_exposure_fraction=float("inf")).validate()


@pytest.mark.parametrize("field", ["risk_amount", "final_risk_fraction"])
def test_risk_calculation_rejects_non_finite_values(field: str) -> None:
    risk = _risk()
    values = {**risk.__dict__, field: float("nan")}
    with pytest.raises(ValueError, match="finite"):
        evaluate_pretrade_risk(
            RiskCalculation(**values),
            account=_account(),
            limits=RiskLimits(),
            proposed_notional=1_000.0,
            strategy_state=StrategyRiskState.RISK_REVIEW,
            research_valid=True,
        )


def test_default_limits_match_governed_profile() -> None:
    limits = RiskLimits()
    limits.validate()

    assert limits.max_daily_loss_fraction == 0.02
    assert limits.max_drawdown_fraction == 0.06
    assert limits.max_strategy_loss_fraction == 0.03
    assert limits.max_trade_loss_fraction == 0.005
    assert limits.target_trade_risk_fraction == 0.0025
    assert limits.max_portfolio_open_risk_fraction == 0.01
    assert limits.max_gross_exposure_fraction == 3.0
    assert limits.max_single_instrument_exposure_fraction == 1.5


def test_clean_account_passes_and_has_deterministic_audit_hash() -> None:
    first = _evaluate()
    second = _evaluate()

    assert first.allowed
    assert first.status == "PASS"
    assert first.violations == ()
    assert first.audit_hash == second.audit_hash
    assert len(first.audit_hash) == 64
    json.dumps(first.to_dict())


def test_daily_equity_loss_is_a_hard_block() -> None:
    decision = _evaluate(account=_account(current_equity=9_700.0))

    assert not decision.allowed
    assert RiskViolationCode.DAILY_LOSS_LIMIT in {
        item.code for item in decision.violations
    }
    assert decision.daily_loss_fraction == pytest.approx(0.03)


def test_high_water_mark_drawdown_is_a_hard_block() -> None:
    decision = _evaluate(
        account=_account(current_equity=9_300.0, high_water_mark=10_000.0)
    )

    assert not decision.allowed
    assert RiskViolationCode.MAX_DRAWDOWN in {
        item.code for item in decision.violations
    }
    assert decision.drawdown_fraction == pytest.approx(0.07)


def test_strategy_loss_is_a_hard_block() -> None:
    decision = _evaluate(account=_account(strategy_pnl=-310.0))

    assert not decision.allowed
    assert RiskViolationCode.MAX_STRATEGY_LOSS in {
        item.code for item in decision.violations
    }


def test_trade_risk_limit_is_a_hard_block() -> None:
    decision = _evaluate(risk=_risk(final_risk_fraction=0.006))

    assert not decision.allowed
    assert RiskViolationCode.MAX_TRADE_RISK in {
        item.code for item in decision.violations
    }


def test_open_risk_budget_includes_proposed_trade() -> None:
    decision = _evaluate(
        account=_account(open_risk_amount=80.0),
        risk=_risk(final_risk_fraction=0.0025),
    )

    assert not decision.allowed
    assert RiskViolationCode.MAX_PORTFOLIO_OPEN_RISK in {
        item.code for item in decision.violations
    }
    assert decision.projected_open_risk_fraction == pytest.approx(0.0105)


def test_gross_exposure_limit_includes_proposed_notional() -> None:
    decision = _evaluate(
        account=_account(gross_exposure=29_900.0),
        proposed_notional=500.0,
    )

    assert not decision.allowed
    assert RiskViolationCode.MAX_GROSS_EXPOSURE in {
        item.code for item in decision.violations
    }


def test_single_instrument_exposure_limit_includes_proposed_notional() -> None:
    decision = _evaluate(
        account=_account(single_instrument_exposure=14_900.0),
        proposed_notional=500.0,
    )

    assert not decision.allowed
    assert RiskViolationCode.MAX_SINGLE_INSTRUMENT_EXPOSURE in {
        item.code for item in decision.violations
    }


def test_kill_switch_is_a_hard_block() -> None:
    decision = _evaluate(
        account=_account(
            kill_switch_active=True,
            kill_switch_reason="operator emergency",
        )
    )

    assert not decision.allowed
    assert RiskViolationCode.KILL_SWITCH_ACTIVE in {
        item.code for item in decision.violations
    }


def test_invalid_research_is_hard_blocked() -> None:
    decision = _evaluate(research_valid=False)

    assert not decision.allowed
    assert RiskViolationCode.RESEARCH_INVALID in {
        item.code for item in decision.violations
    }


@pytest.mark.parametrize(
    "state",
    [
        StrategyRiskState.RESEARCH,
        StrategyRiskState.VALIDATED,
        StrategyRiskState.SUSPENDED,
        StrategyRiskState.RETIRED,
    ],
)
def test_non_tradeable_strategy_states_are_blocked(
    state: StrategyRiskState,
) -> None:
    decision = _evaluate(strategy_state=state)

    assert not decision.allowed
    assert RiskViolationCode.STRATEGY_STATE_BLOCKED in {
        item.code for item in decision.violations
    }


def test_missing_notional_is_fail_closed() -> None:
    decision = _evaluate(proposed_notional=None)

    assert not decision.allowed
    assert RiskViolationCode.PROPOSED_NOTIONAL_REQUIRED in {
        item.code for item in decision.violations
    }


def test_risk_equity_mismatch_is_blocked() -> None:
    decision = _evaluate(
        risk=_risk(account_equity=20_000.0, final_risk_fraction=0.0025)
    )

    assert not decision.allowed
    assert RiskViolationCode.RISK_EQUITY_MISMATCH in {
        item.code for item in decision.violations
    }


def test_near_limit_usage_emits_warning_without_blocking() -> None:
    decision = _evaluate(
        account=_account(current_equity=9_838.0),
        risk=_risk(account_equity=9_838.0, final_risk_fraction=0.001),
    )

    assert decision.allowed
    assert any("DAILY_LOSS_LIMIT" in warning for warning in decision.warnings)


def test_strategy_state_machine_forbids_skips() -> None:
    validate_strategy_transition(
        StrategyRiskState.RESEARCH,
        StrategyRiskState.VALIDATED,
    )
    validate_strategy_transition(
        StrategyRiskState.SUSPENDED,
        StrategyRiskState.RISK_REVIEW,
    )

    with pytest.raises(StrategyStateTransitionError):
        validate_strategy_transition(
            StrategyRiskState.VALIDATED,
            StrategyRiskState.PAPER_ELIGIBLE,
        )
