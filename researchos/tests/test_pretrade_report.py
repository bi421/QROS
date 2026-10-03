from __future__ import annotations

from researchos.action import build_pre_trade_report
from researchos.risk import RiskInput, TradeStatistics, calculate_risk


def _risk() -> object:
    return calculate_risk(
        RiskInput(
            asset="XAUUSD",
            direction="UP",
            probability=0.60,
            account_equity=10_000.0,
            trade_statistics=TradeStatistics(150.0, 100.0, 200),
            research_id="R-001",
        )
    )


def test_valid_research_produces_human_review_status() -> None:
    report = build_pre_trade_report(_risk(), research_valid=True)

    assert report.status == "READY_FOR_HUMAN_REVIEW"
    assert report.research_id == "R-001"
    assert report.risk_valid is True


def test_invalid_research_is_blocked() -> None:
    report = build_pre_trade_report(
        _risk(),
        research_valid=False,
        research_limitations=("Probability not calibrated",),
    )

    assert report.status == "BLOCKED_RESEARCH_VALIDATION"
    assert report.risk_valid is True
    assert report.limitations == ("Probability not calibrated",)


def test_zero_risk_is_not_trade_ready() -> None:
    risk = calculate_risk(
        RiskInput(
            asset="XAUUSD",
            direction="UP",
            probability=0.40,
            account_equity=10_000.0,
            trade_statistics=TradeStatistics(150.0, 100.0, 200),
        )
    )
    report = build_pre_trade_report(risk, research_valid=True)

    assert report.status == "NO_POSITIVE_RISK_BUDGET"


def test_report_is_serializable() -> None:
    report = build_pre_trade_report(_risk(), research_valid=True)
    payload = report.to_dict()

    assert payload["schema_version"] == "pretrade.v2"
    assert payload["status"] == "READY_FOR_HUMAN_REVIEW"
