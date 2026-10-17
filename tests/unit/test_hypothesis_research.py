from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from researchos.orchestration.hypothesis_research import (
    HYPOTHESES,
    analyze_trade_dependence,
    claim_final_holdout,
    cost_model_ready,
    evaluate_candidate_gate,
    load_costs,
    register_trial,
    kelly_fraction,
    run_five_overfitting_attacks,
    verify_trial_registry,
)


def test_five_hypotheses_have_rationale_and_at_most_three_parameters() -> None:
    assert len(HYPOTHESES) >= 5
    for item in HYPOTHESES.values():
        assert item["rationale"].strip()
        assert 1 <= len(item["parameters"]) <= 3


def test_cost_template_is_assumed_and_fails_closed() -> None:
    root = Path(__file__).resolve().parents[2]
    costs = load_costs(root / "config" / "costs.yaml")
    ready, missing = cost_model_ready(costs)
    assert costs["status"] == "UNVERIFIED"
    assert not ready
    assert missing


def test_trial_registry_is_append_only_hash_chained(tmp_path: Path) -> None:
    path = tmp_path / "trial_registry.jsonl"
    digest = hashlib.sha256(b"dataset").hexdigest()
    first = register_trial(
        path, hypothesis_id="session_liquidity", data_sha256=digest, code_sha="abc123"
    )
    second = register_trial(
        path, hypothesis_id="vol_compression_expansion", data_sha256=digest, code_sha="abc123"
    )
    assert first["trial_number"] == 1
    assert second["trial_number"] == 2
    assert second["previous_record_sha256"] == first["record_sha256"]
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    assert verify_trial_registry(path) == {"valid": True, "records": 2, "errors": []}
    tampered = path.read_text(encoding="utf-8").replace("abc123", "def456", 1)
    path.write_text(tampered, encoding="utf-8")
    assert not verify_trial_registry(path)["valid"]
    with pytest.raises(ValueError, match="TRIAL_REGISTRY_INTEGRITY_FAILURE"):
        register_trial(
            path, hypothesis_id="session_liquidity", data_sha256=digest, code_sha="abc123"
        )


def test_final_holdout_can_only_be_claimed_once(tmp_path: Path) -> None:
    lock = tmp_path / "final_holdout.lock.json"
    digest = hashlib.sha256(b"candidate").hexdigest()
    assert claim_final_holdout(lock, candidate_sha256=digest)["status"] == "CLAIMED_ONCE"
    with pytest.raises(RuntimeError, match="FINAL_HOLDOUT_ALREADY_CONSUMED"):
        claim_final_holdout(lock, candidate_sha256=digest)


def test_candidate_gate_fails_closed_on_missing_metrics() -> None:
    result = evaluate_candidate_gate({})
    assert result["status"] == "REJECTED"
    assert result["execution_enabled"] is False
    assert len(result["failed_reasons"]) == len(result["checks"])


def test_overfitting_attacks_return_all_five_diagnostics_without_authorizing_execution() -> None:
    result = run_five_overfitting_attacks(
        [1.0, -0.2, 0.5, 0.7, -0.1, 0.3, 0.4, -0.2, 0.8, 0.1],
        asset_labels=["A", "A", "B", "B", "A", "B", "A", "B", "A", "B"],
        regime_labels=["trend", "range"] * 5,
        chunks=5,
        omission_repetitions=100,
        seed=17,
    )
    assert result["status"] == "DIAGNOSTIC_ONLY"
    assert result["execution_enabled"] is False
    assert set(result["attacks"]) == {
        "best_asset_removal",
        "time_chunk_stability",
        "best_regime_removal",
        "top_five_trades_removal",
        "random_trade_omission",
    }


def test_trade_dependence_and_kelly_are_diagnostics_only() -> None:
    dependence = analyze_trade_dependence([1, -1, -1, 1, 1, -1, 0])
    assert dependence["position_sizing_changed"] is False
    assert dependence["loss_streak_conditional_win_rates"]["2"]["observed_cases"] >= 1
    sizing = kelly_fraction(0.3, 1.5)
    assert sizing["applied_fraction_after_cap"] == 0
    assert sizing["decision"] == "NO_BET"


def test_candidate_gate_requires_every_predeclared_condition() -> None:
    metrics = {
        "net_expectancy": 0.2,
        "ci_lower": 0.01,
        "wf_positive_fold_fraction": 0.75,
        "net_expectancy_cost_1_5x": 0.01,
        "multiple_testing_significant": True,
        "beats_negative_controls": True,
        "largest_year_or_regime_profit_share": 0.4,
        "cost_model_verified": True,
        "plateau_stable": True,
    }
    assert evaluate_candidate_gate(metrics)["status"] == "CANDIDATE"
    metrics["net_expectancy_cost_1_5x"] = -0.01
    assert evaluate_candidate_gate(metrics)["status"] == "REJECTED"
